"""Application service. No generated output is promoted into knowledge."""
import asyncio
from dataclasses import dataclass
from .provider import Request, ProviderUnavailable, DisabledCodex


@dataclass(frozen=True)
class Answer:
    case: int
    text: str
    evidence: tuple


def source_link(case, resolution=True):
    channel = case['resolution_channel'] if resolution else case['source_channel']
    message = case['resolution_message'] if resolution else case['question_message']
    return f"https://discord.com/channels/{case['guild']}/{channel}/{message}"


class Service:
    def __init__(self, store, provider, timeout=20):
        self.store = store
        self.provider = provider
        self.timeout = timeout

    async def ask(self, s, question, source_message):
        with self.store.operation(s) as pending:
            return await self._ask(s, question, source_message, pending)

    async def _ask(self, s, question, source_message, pending):
        self.store.require_enabled(s)
        question = self.store.text(question)
        history = tuple(self.store.history(s))
        case = self.store.candidate(s, question, source_message)
        evidence = tuple(self.store.search_knowledge(s, question))
        try:
            reply = await asyncio.wait_for(
                self.provider.answer(Request(s.tenant, question, history, evidence)), self.timeout)
            allowed = {item['id'] for item in evidence}
            if not isinstance(reply.text, str) or not reply.text.strip() or not set(reply.case_ids).issubset(allowed):
                raise ProviderUnavailable("공급자 응답/출처 검증 실패")
            body = reply.text[:1000]
            cited = tuple(item for item in evidence if item['id'] in reply.case_ids)
            if cited:
                body += "\n출처: " + " ".join(source_link(item) for item in cited)
        except (ProviderUnavailable, asyncio.TimeoutError) as exc:
            body = "공급자 비활성 또는 응답/출처 검증 실패: 생성 답변 없음"
            if isinstance(self.provider, DisabledCodex):
                body = "Codex 실시간 생성 비활성: 안전한 연동 및 사용 조건 검증 대기"
            elif isinstance(exc, asyncio.TimeoutError):
                body = "공급자 시간 초과: 생성 답변 없음"
            body += "\n생성 답변이 아닙니다. 질문과 어휘가 일치하는 이 채널의 확정 사례 (의미/정확성 보증 아님):"
            if not evidence:
                body += "\n검색 범위에서 일치하는 확정 사례를 찾지 못했습니다. 다른 핵심어로 질문하거나 해결 후 /resolved로 직접 등록하세요."
            for item in evidence:
                body += f"\n사례 #{item['id']}: {item['solution'][:180]}\n{source_link(item)}"
        except Exception:
            # Do not return provider exception strings: they can contain secrets.
            body = "공급자 오류: 생성 답변을 제공하지 않았습니다."
        pending.check()
        return Answer(case, f"후보 사례 #{case} (자동 학습 아님)\n{body}", evidence)
