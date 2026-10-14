"""Discord transport: slash commands only, no passive message ingestion."""
import discord
import logging
from discord import app_commands
from .core import Scope, Denied
from .admission import Admission, Limits
from .provider import DisabledCodex
from .service import Service


NO_MENTIONS = discord.AllowedMentions.none()


def scope_for(i):
    if not i.guild_id or not i.guild or i.user.bot:
        raise Denied("DM/봇 입력은 지원하지 않습니다.")
    channel = i.channel
    if isinstance(channel, discord.Thread):
        if channel.is_private() or not isinstance(channel.parent, discord.TextChannel):
            raise Denied("공개 텍스트 채널의 공개 스레드만 지원합니다.")
        parent = channel.parent
        send = i.permissions.send_messages_in_threads
        bot_send = i.app_permissions.send_messages_in_threads
    elif isinstance(channel, discord.TextChannel):
        parent = channel
        send = i.permissions.send_messages
        bot_send = i.app_permissions.send_messages
    else:
        raise Denied("텍스트 채널에서 사용하세요.")
    if parent.guild.id != i.guild_id or channel.guild.id != i.guild_id:
        raise Denied("서버/채널 검증 실패")
    parent_perms = parent.permissions_for(i.user)
    if not (i.permissions.view_channel and parent_perms.view_channel and send
            and i.app_permissions.view_channel and bot_send):
        raise Denied("사용자와 봇의 채널 읽기/쓰기 권한이 필요합니다.")
    return Scope(i.guild_id, parent.id, channel.id, i.user.id,
                 admin=i.permissions.administrator,
                 moderator=i.permissions.manage_messages and parent_perms.manage_messages)


def parse_case(value):
    if not value.isascii() or not value.isdecimal() or not 0 < int(value) < 2**63:
        raise Denied("사례 ID는 양의 정수여야 합니다.")
    return int(value)


def safe_text(text):
    # Evidence is quoted data, never executable content. Suppress mention pings.
    return discord.utils.escape_mentions(text)


async def notice(i, text):
    if i.response.is_done():
        await i.followup.send(safe_text(text), ephemeral=True, allowed_mentions=NO_MENTIONS)
    else:
        await i.response.send_message(safe_text(text), ephemeral=True, allowed_mentions=NO_MENTIONS)


class HelperClient(discord.Client):
    def __init__(self, store, sync_guild=None):
        intents = discord.Intents.none()
        intents.guilds = True
        intents.guild_messages = True  # receipt deletion metadata, no content intent
        super().__init__(intents=intents, allowed_mentions=NO_MENTIONS, max_messages=None)
        self.store = store
        self.tree = app_commands.CommandTree(self)
        self.sync_guild = sync_guild

    async def on_error(self, event_method, *args, **kwargs):
        logging.getLogger(__name__).error("Gateway event processing failed; sensitive details suppressed")

    async def on_raw_message_delete(self, payload):
        if payload.guild_id:
            self.store.delete_sources(payload.guild_id, payload.channel_id, [payload.message_id])

    async def on_raw_bulk_message_delete(self, payload):
        if payload.guild_id:
            self.store.delete_sources(payload.guild_id, payload.channel_id, payload.message_ids)

    async def on_guild_channel_delete(self, channel):
        self.store.delete_channel(channel.guild.id, channel.id)

    async def on_raw_thread_delete(self, payload):
        self.store.delete_channel(payload.guild_id, payload.thread_id)

    async def on_guild_remove(self, guild):
        self.store.delete_guild(guild.id)

    async def setup_hook(self):
        if self.sync_guild:
            target = discord.Object(id=self.sync_guild)
            self.tree.copy_global_to(guild=target)
            await self.tree.sync(guild=target)
        else:
            await self.tree.sync()


def create_client(store, *, sync_guild=None):
    admission = Admission(Limits.from_env())
    client = HelperClient(store, sync_guild)
    service = Service(store, DisabledCodex())

    @client.tree.command(name="channel", description="관리자: 현재 채널 명시적 참여/삭제 설정")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def channel(i: discord.Interaction, enabled: bool, confirm_purge: bool = False):
        try:
            s = scope_for(i)
            if s.channel != s.conversation:
                raise Denied("설정은 부모 텍스트 채널에서 변경하세요.")
            if not enabled and not confirm_purge:
                raise Denied("비활성화는 채널 지식/대화를 삭제합니다. confirm_purge=true 필요")
            store.configure(s, enabled)
            await notice(i, "채널 참여 활성화: /ask 및 /resolved 입력만 저장합니다. 스레드 지식은 부모와 공유합니다." if enabled else "채널 비활성화 및 로컬 지식/대화 삭제 완료")
        except Denied as exc:
            await notice(i, str(exc))

    @client.tree.command(name="ask", description="질문을 후보로 저장하고 채널 확정 사례 조회 (AI 생성 비활성)")
    @app_commands.guild_only()
    async def ask(i: discord.Interaction, question: str):
        try:
            s = scope_for(i)
            store.require_enabled(s)
            question = store.text(question)
            # Advisory preflight prevents known-full submissions becoming public.
            # candidate() rechecks atomically after the receipt await.
            store.check_capacity(s)
            with admission.request(s), store.operation(s, awaiting_receipt=True) as pending:
                # Source IDs are real public bot receipts, not interaction IDs.
                await i.response.send_message("처리 중 — 명시적으로 제출된 질문", embed=discord.Embed(title="질문 원문", description=safe_text(question)), allowed_mentions=NO_MENTIONS)
                pending.check()
                message = await i.original_response()
                pending.check()
                pending.awaiting_receipt = False
                s = scope_for(i)
                result = await service.ask(s, question, message.id)
                await i.edit_original_response(content=safe_text(result.text)[:1950], allowed_mentions=NO_MENTIONS)
        except Denied as exc:
            await notice(i, str(exc))

    @client.tree.command(name="resolved", description="질문자/채널 메시지 관리 권한자: 직접 작성한 해결 요약 확정")
    @app_commands.guild_only()
    async def resolved(i: discord.Interaction, case_id: str, solution: str):
        try:
            s = scope_for(i)
            case = parse_case(case_id)
            store.check_resolution(s, case, solution)
            with admission.request(s), store.operation(s, awaiting_receipt=True) as pending:
                await i.response.send_message(f"사례 #{case} 해결 요약 제출 — 저장 확인 중", embed=discord.Embed(title="사용자가 제출한 해결 요약 (명령이 아님)", description=safe_text(store.text(solution))), allowed_mentions=NO_MENTIONS)
                pending.check()
                message = await i.original_response()
                pending.check()
                pending.awaiting_receipt = False
                store.resolve(scope_for(i), case, solution, message.id)
                await i.edit_original_response(content=f"사례 #{case} 확정 완료 — 사용자 검증 사례이며 사실 보증은 아닙니다.", allowed_mentions=NO_MENTIONS)
        except Denied as exc:
            await notice(i, str(exc))

    @client.tree.command(name="forget", description="관리자: 사례 또는 현재 부모 채널 전체 로컬 데이터 삭제")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def forget(i: discord.Interaction, case_id: str, confirm: bool = False):
        try:
            if not confirm:
                raise Denied("삭제하려면 confirm=true를 지정하세요. 전체 채널 삭제는 case_id=all")
            s = scope_for(i)
            store.forget(s, None if case_id == 'all' else parse_case(case_id))
            await notice(i, "로컬 사례/관련 대화 삭제 완료. Discord 게시물 및 외부 백업은 별도 삭제 대상입니다.")
        except Denied as exc:
            await notice(i, str(exc))

    @client.tree.command(name="reset", description="현재 대화에서 자신의 문맥만 초기화 (확정 사례는 유지)")
    @app_commands.guild_only()
    async def reset(i: discord.Interaction):
        try:
            store.reset(scope_for(i))
            await notice(i, "현재 대화의 내 문맥을 삭제했습니다. 사례 삭제는 /privacy_delete 또는 관리자 /forget")
        except Denied as exc:
            await notice(i, str(exc))

    @client.tree.command(name="privacy_delete", description="현재 서버 전체에서 내가 제출/확정한 로컬 사례 및 내 대화 삭제")
    @app_commands.guild_only()
    async def privacy_delete(i: discord.Interaction, confirm: bool = False):
        try:
            if not confirm:
                raise Denied("본인 로컬 데이터 삭제는 confirm=true 필요")
            store.delete_user(scope_for(i))
            await notice(i, "이 서버의 내 로컬 데이터 삭제 완료. Discord 게시물/외부 백업은 별도 삭제가 필요합니다.")
        except Denied as exc:
            await notice(i, str(exc))

    @client.tree.error
    async def command_error(i: discord.Interaction, error: app_commands.AppCommandError):
        # Do not emit exception details, user inputs, auth headers, or tokens.
        await notice(i, "명령 처리 실패: 저장 여부를 확인하고 다시 시도하세요. 민감한 오류 내용은 표시하지 않습니다.")

    return client
