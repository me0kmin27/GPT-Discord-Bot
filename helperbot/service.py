"""Application service. No generated output is promoted into knowledge."""
import asyncio

from dataclasses import dataclass
from .provider import Request, ProviderUnavailable, DisabledCodex
from .async_utils import wait_owned
from .inference_probe import safe_failure


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
    def __init__(self, store, provider, timeout=None):
        self.store = store
        self.provider = provider
        # A phased provider owns preparation/generation deadlines. An explicit
        # Service override remains available for tests/custom applications.
        self.timeout = timeout
        if timeout is None and getattr(provider, 'manages_deadlines', False) is not True:
            self.timeout = 20

    async def ask(self, s, question, source_message):
        with self.store.operation(s) as pending:
            return await self._ask(s, question, source_message, pending)

    async def _ask(self, s, question, source_message, pending):
        self.store.require_enabled(s)
        question = self.store.text(question)
        history = tuple(self.store.history(s))
        case = self.store.candidate(s, question, source_message)
        evidence = tuple(self.store.search_knowledge(s, question))
        generated = None
        started = asyncio.get_running_loop().time()
        try:
            reply = await wait_owned(
                self.provider.answer(Request(s.tenant, question, history, evidence)), self.timeout, stage='service')
            allowed = {item['id'] for item in evidence}
            if (not isinstance(reply.text, str) or not reply.text.strip()
                    or len(reply.text) > 1000 or '\x00' in reply.text
                    or not isinstance(reply.case_ids, (tuple, list)) or len(reply.case_ids) > 3
                    or any(type(key) is not int for key in reply.case_ids)
                    or len(set(reply.case_ids)) != len(reply.case_ids)
                    or not set(reply.case_ids).issubset(allowed)):
                raise ProviderUnavailable("공급자 응답/출처 검증 실패")
            body = reply.text.strip()
            cited = tuple(item for item in evidence if item['id'] in reply.case_ids)
            if cited:
                body += "\n출처: " + " ".join(source_link(item) for item in cited)
            generated = reply.text.strip()
        except (ProviderUnavailable, asyncio.TimeoutError, TimeoutError) as exc:
            failure = safe_failure(exc)
            body = "공급자 비활성 또는 응답/출처 검증 실패: 생성 답변 없음"
            if isinstance(self.provider, DisabledCodex):
                body = "Codex 실시간 생성 비활성: 안전한 연동 및 사용 조건 검증 대기"
            elif failure['category'] == 'deadline_exceeded':
                body = "공급자 시간 초과: 생성 답변 없음"
            elif isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
                body = "공급자 내부 시간 초과: 생성 답변 없음 (봇 제한 시간 만료 여부는 확인되지 않았습니다)"
            body += f"\n진단 [{failure['stage']}/{failure['category']}]: 운영자는 안전한 추론 진단 명령으로 확인하세요."
            if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
                body += (f"\nservice_elapsed_ms={max(0, int((asyncio.get_running_loop().time() - started) * 1000))}"
                         f" service_deadline_ms={None if self.timeout is None else int(self.timeout * 1000)}"
                         f" origin={failure['timeout_origin']}")
                if failure['elapsed_ms'] is not None:
                    body += f" elapsed_ms={failure['elapsed_ms']} deadline_ms={failure['deadline_ms']}"
            body += "\n생성 답변이 아닙니다. 질문과 어휘가 일치하는 이 채널의 확정 사례 (의미/정확성 보증 아님):"
            if not evidence:
                body += "\n검색 범위에서 일치하는 확정 사례를 찾지 못했습니다. 사례 부족은 공급자 실패의 원인이 아닙니다. 잠시 후 재시도하거나 운영자에게 위 진단을 전달하세요."
            for item in evidence:
                body += f"\n사례 #{item['id']}: {item['solution'][:180]}\n{source_link(item)}"
        except Exception as exc:
            # Do not return provider exception strings: they can contain secrets.
            failure = safe_failure(exc)
            body = ("공급자 오류: 생성 답변을 제공하지 않았습니다."
                    f"\n진단 [{failure['stage']}/{failure['category']}]: 운영자는 안전한 추론 진단 명령으로 확인하세요.")
        pending.check()
        if generated is not None:
            # Outside the provider error handler: storage failure is not success.
            self.store.save_generated_answer(s, case, generated, pending,
                                             tuple(item['id'] for item in evidence))
        return Answer(case, f"후보 사례 #{case} (자동 학습 아님)\n{body}", evidence)
