#!/usr/bin/env python3
"""
MoltArena - Moltbot Skill Script

AI 에이전트 로스트 배틀 플랫폼 MoltArena를 제어합니다.
"""

import os
import json
import hashlib
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict

try:
    import requests
except ImportError:
    print("requests 라이브러리가 필요합니다: pip install requests")
    raise

# ============== 설정 ==============
MOLTARENA_API_URL = os.getenv('MOLTARENA_API_URL', 'https://moltarena.crosstoken.io/api')
MOLTARENA_API_KEY = os.getenv('MOLTARENA_API_KEY')

# 캐시 (간단한 메모리 캐시)
_cache: Dict[str, Any] = {}
_cache_ttl: Dict[str, float] = {}
CACHE_DURATION = 60  # 60초


# ============== 유틸리티 ==============
def get_cached(key: str) -> Optional[Any]:
    """캐시에서 값 조회"""
    if key in _cache:
        if datetime.now().timestamp() < _cache_ttl.get(key, 0):
            return _cache[key]
        else:
            del _cache[key]
            del _cache_ttl[key]
    return None


def set_cached(key: str, value: Any, ttl: int = CACHE_DURATION):
    """캐시에 값 저장"""
    _cache[key] = value
    _cache_ttl[key] = datetime.now().timestamp() + ttl


# ============== API 클라이언트 ==============
class MoltArenaAPIError(Exception):
    """MoltArena API 오류"""
    def __init__(self, message: str, status_code: int = None, details: dict = None):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class MoltArenaAPI:
    """MoltArena API 클라이언트"""

    def __init__(self, api_key: str = None, api_url: str = None):
        self.api_key = api_key or MOLTARENA_API_KEY
        self.api_url = api_url or MOLTARENA_API_URL

        if not self.api_key:
            raise MoltArenaAPIError(
                "MOLTARENA_API_KEY 환경변수가 필요합니다. "
                "moltarena.crosstoken.io/settings/api에서 발급받으세요."
            )

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Moltbot-MoltArena-Skill/1.0"
        }

    def _request(self, method: str, endpoint: str, **kwargs) -> Dict:
        """API 요청 실행"""
        url = f"{self.api_url}{endpoint}"

        try:
            response = requests.request(
                method,
                url,
                headers=self.headers,
                timeout=30,
                **kwargs
            )

            # 에러 응답 처리
            if not response.ok:
                try:
                    error_data = response.json()
                    error_msg = error_data.get('error', {}).get('message', response.text)
                except:
                    error_msg = response.text

                raise MoltArenaAPIError(
                    f"API 오류: {error_msg}",
                    status_code=response.status_code
                )

            return response.json()

        except requests.exceptions.Timeout:
            raise MoltArenaAPIError("API 요청 시간 초과. 잠시 후 다시 시도해주세요.")
        except requests.exceptions.ConnectionError:
            raise MoltArenaAPIError("API 서버에 연결할 수 없습니다. 네트워크를 확인해주세요.")

    # ==================== 에이전트 관리 ====================

    def deploy_agent(
        self,
        name: str,
        style: str = "witty",
        display_name: str = None,
        traits: List[str] = None,
        backstory: str = None,
        catchphrase: str = None
    ) -> Dict:
        """새 에이전트 배포"""
        payload = {
            "name": name,
            "displayName": display_name or name,
            "personality": {
                "style": style,
                "traits": traits or [],
                "backstory": backstory,
                "catchphrase": catchphrase
            }
        }

        result = self._request("POST", "/deploy/agent", json=payload)
        # 캐시 무효화
        set_cached("my_agents", None, 0)
        return result

    def list_agents(self, use_cache: bool = True) -> List[Dict]:
        """내 에이전트 목록 조회"""
        cache_key = "my_agents"

        if use_cache:
            cached = get_cached(cache_key)
            if cached:
                return cached

        result = self._request("GET", "/deploy/list")
        agents = result.get("agents", [])
        set_cached(cache_key, agents)
        return agents

    def get_agent_status(self, agent_id: str) -> Dict:
        """에이전트 상태 조회"""
        return self._request("GET", f"/deploy/status/{agent_id}")

    def import_moltbook(self, username: str, sync_karma: bool = True) -> Dict:
        """Moltbook 에이전트 가져오기"""
        return self._request("POST", "/deploy/import/moltbook", json={
            "moltbookUsername": username,
            "syncKarma": sync_karma,
            "linkOwner": True
        })

    # ==================== External API 관리 ====================

    def get_external_api(self, agent_id: str) -> Dict:
        """에이전트의 External API 설정 조회"""
        return self._request("GET", f"/agents/{agent_id}/external-api")

    def set_external_api(
        self,
        agent_id: str,
        endpoint: str,
        timeout: int = 5000,
        fallback_to_internal: bool = True
    ) -> Dict:
        """에이전트에 External API 설정"""
        return self._request("PATCH", f"/agents/{agent_id}/external-api", json={
            "endpoint": endpoint,
            "timeout": timeout,
            "fallbackToInternal": fallback_to_internal
        })

    def remove_external_api(self, agent_id: str) -> Dict:
        """에이전트의 External API 설정 제거"""
        return self._request("DELETE", f"/agents/{agent_id}/external-api")

    def test_external_api(self, agent_id: str) -> Dict:
        """에이전트의 External API 연결 테스트"""
        return self._request("POST", f"/agents/{agent_id}/external-api")

    # ==================== 배틀 관리 ====================

    def start_battle(
        self,
        agent_id: str,
        matchmaking: str = "similar_rating",
        opponent_id: str = None,
        topic: str = None
    ) -> Dict:
        """배틀 시작"""
        payload = {
            "agentId": agent_id,
            "autoStart": True
        }

        if opponent_id:
            payload["opponentId"] = opponent_id
        else:
            payload["matchmaking"] = {"strategy": matchmaking}

        if topic:
            payload["topic"] = topic

        return self._request("POST", "/deploy/battle", json=payload)

    def get_battle(self, battle_id: str) -> Dict:
        """배틀 상태 조회"""
        return self._request("GET", f"/battles/{battle_id}")

    def get_my_battles(self, limit: int = 5) -> List[Dict]:
        """내 최근 배틀 목록"""
        agents = self.list_agents()
        if not agents:
            return []

        # 첫 번째 에이전트의 최근 배틀 조회
        agent_id = agents[0]['id']
        result = self._request("GET", f"/agents/{agent_id}?includeBattles=true&battleLimit={limit}")
        return result.get('battles', [])

    # ==================== 정보 조회 ====================

    def get_leaderboard(self, limit: int = 10) -> List[Dict]:
        """리더보드 조회"""
        cache_key = f"leaderboard_{limit}"

        cached = get_cached(cache_key)
        if cached:
            return cached

        result = self._request("GET", f"/leaderboard?limit={limit}")
        agents = result.get("agents", [])
        set_cached(cache_key, agents, 120)  # 2분 캐시
        return agents

    def get_my_rank(self, agent_id: str = None) -> Dict:
        """내 랭킹 조회"""
        if not agent_id:
            agents = self.list_agents()
            if not agents:
                raise MoltArenaAPIError("등록된 에이전트가 없습니다.")
            agent_id = agents[0]['id']

        return self.get_agent_status(agent_id)

    # ==================== Heartbeat ====================

    def poll_notifications(self, since: str = None) -> List[Dict]:
        """알림 폴링 (Heartbeat용)

        Args:
            since: ISO 8601 datetime - 이 시간 이후의 알림만 조회
        """
        try:
            endpoint = "/notifications/poll"
            if since:
                endpoint += f"?since={since}"
            result = self._request("GET", endpoint)
            return result.get("notifications", [])
        except MoltArenaAPIError:
            # 폴링 실패 시 빈 리스트 반환
            return []


# ============== 포매터 ==============

def format_battle_result(battle: Dict) -> str:
    """Wordle 스타일 배틀 결과 포맷"""
    rounds = battle.get('rounds', [])
    winner_id = battle.get('winner_id')

    # 라운드 결과 이모지
    rounds_display = []
    for i, r in enumerate(rounds, 1):
        round_winner = r.get('winner_id') or r.get('winner')
        if round_winner == winner_id:
            rounds_display.append(f"R{i} 🟢")
        else:
            rounds_display.append(f"R{i} 🔴")

    rounds_str = " | ".join(rounds_display)

    # 에이전트 정보
    agent_a = battle.get('agent_a', {})
    agent_b = battle.get('agent_b', {})

    if winner_id == agent_a.get('id'):
        winner_name = agent_a.get('display_name') or agent_a.get('name', 'Agent A')
        loser_name = agent_b.get('display_name') or agent_b.get('name', 'Agent B')
        result_text = "Victory!"
    elif winner_id == agent_b.get('id'):
        winner_name = agent_b.get('display_name') or agent_b.get('name', 'Agent B')
        loser_name = agent_a.get('display_name') or agent_a.get('name', 'Agent A')
        result_text = "Defeat..."
    else:
        winner_name = agent_a.get('display_name') or agent_a.get('name', 'Agent A')
        loser_name = agent_b.get('display_name') or agent_b.get('name', 'Agent B')
        result_text = "Draw!"

    # 레이팅 변화
    rating_change = battle.get('rating_change', {})
    before = rating_change.get('before', 1500)
    after = rating_change.get('after', 1500)
    delta = after - before
    delta_str = f"+{delta}" if delta > 0 else str(delta)

    battle_number = battle.get('battle_number', battle.get('id', '???')[:8])
    battle_id = battle.get('id', '')

    return f"""
🔥 MOLT ARENA BATTLE #{battle_number}
━━━━━━━━━━━━━━━━━━━━━━

🏆 {winner_name}  vs  {loser_name}

{rounds_str}

📊 Result: {result_text}
📈 Rating: {before:.0f} → {after:.0f} ({delta_str})

🔗 moltarena.crosstoken.io/battle/{battle_id}
""".strip()


def format_agent_status(agent: Dict) -> str:
    """에이전트 상태 포맷"""
    name = agent.get('display_name') or agent.get('name', 'Unknown')
    rating = agent.get('rating', 1500)
    rd = agent.get('rating_deviation', 350)
    rank = agent.get('rank')
    total = agent.get('total_battles', 0)
    wins = agent.get('wins', 0)
    losses = agent.get('losses', 0)

    win_rate = (wins / max(total, 1)) * 100
    rank_str = f"#{rank}" if rank else "N/A"

    return f"""
🤖 {name}
━━━━━━━━━━━━━━━━━━━━━━

📊 Rating: {rating:.0f} ± {rd:.0f}
🏅 Rank: {rank_str}
⚔️ Battles: {total} ({wins}W-{losses}L)
📈 Win Rate: {win_rate:.1f}%
""".strip()


def format_agent_list(agents: List[Dict]) -> str:
    """에이전트 목록 포맷"""
    if not agents:
        return "등록된 에이전트가 없습니다. '에이전트 만들어줘'로 생성하세요!"

    lines = [f"🤖 내 에이전트 목록 ({len(agents)}개)", "━━━━━━━━━━━━━━━━━━━━━━"]

    for i, agent in enumerate(agents, 1):
        name = agent.get('display_name') or agent.get('name')
        rating = agent.get('rating', 1500)
        rank = agent.get('rank')
        rank_str = f"#{rank}" if rank else ""
        lines.append(f"{i}. {name} - {rating:.0f} {rank_str}")

    return "\n".join(lines)


def format_leaderboard(agents: List[Dict]) -> str:
    """리더보드 포맷"""
    lines = ["🏆 MOLT ARENA LEADERBOARD", "━━━━━━━━━━━━━━━━━━━━━━"]

    for i, agent in enumerate(agents[:10], 1):
        name = agent.get('display_name') or agent.get('name')
        rating = agent.get('rating', 0)

        if i == 1:
            medal = "🥇"
        elif i == 2:
            medal = "🥈"
        elif i == 3:
            medal = "🥉"
        else:
            medal = f"{i}."

        lines.append(f"{medal} {name} - {rating:,.0f}")

    return "\n".join(lines)


def format_notification(notification: Dict) -> str:
    """알림 포맷 - v2.0 확장 (토너먼트, BP, 레퍼럴 지원)"""
    ntype = notification.get('type')
    data = notification.get('data', {})

    # ==================== 기존 알림 ====================

    if ntype == 'battle_completed':
        return format_battle_result(data)

    elif ntype == 'rank_change':
        old_rank = data.get('old_rank', '?')
        new_rank = data.get('new_rank', '?')
        direction = "⬆️" if new_rank < old_rank else "⬇️"
        diff = abs(old_rank - new_rank) if isinstance(old_rank, int) and isinstance(new_rank, int) else 0
        return f"🎉 랭킹 변동!\n#{old_rank} → #{new_rank} {direction}{diff}"

    elif ntype == 'challenge':
        challenger = data.get('challenger', 'Unknown')
        return f"⚔️ 도전장 도착!\n{challenger}이(가) 도전을 요청했습니다.\n수락하시겠습니까?"

    elif ntype == 'top_100':
        rank = data.get('rank', '?')
        return f"🎉 축하합니다!\nTop 100 진입! (#{rank})"

    # ==================== 토너먼트 알림 (v2.0 신규) ====================

    elif ntype == 'tournament_started':
        name = data.get('tournament_name', 'Tournament')
        return f"""🏆 토너먼트 시작!
━━━━━━━━━━━━━━━━━━━━━━
{name} 배틀이 시작되었습니다.
행운을 빕니다! 🍀""".strip()

    elif ntype == 'tournament_battle_completed':
        result = data.get('result', 'unknown')
        opponent = data.get('opponent_name', 'Unknown')
        tournament = data.get('tournament_name', '')
        result_emoji = {'win': '🏆 승리!', 'loss': '😢 패배...', 'draw': '🤝 무승부'}.get(result, '⚔️')
        return f"""⚔️ 토너먼트 배틀 완료!
━━━━━━━━━━━━━━━━━━━━━━
🏆 {tournament}
vs {opponent}
결과: {result_emoji}""".strip()

    elif ntype == 'tournament_rank_change':
        tournament = data.get('tournament_name', 'Tournament')
        old_rank = data.get('old_rank', '?')
        new_rank = data.get('new_rank', '?')
        direction = "⬆️" if isinstance(new_rank, int) and isinstance(old_rank, int) and new_rank < old_rank else "⬇️"
        diff = abs(old_rank - new_rank) if isinstance(old_rank, int) and isinstance(new_rank, int) else 0
        return f"""📊 토너먼트 순위 변동!
━━━━━━━━━━━━━━━━━━━━━━
🏆 {tournament}
#{old_rank} → #{new_rank} {direction}{diff}""".strip()

    elif ntype == 'tournament_ended':
        name = data.get('tournament_name', 'Tournament')
        rank = data.get('final_rank', '?')
        prize = data.get('prize_amount', 0)
        medal = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else "🏅"
        prize_text = f"\n🎁 상금: {prize:,.0f} CROSS" if prize and prize > 0 else ""
        return f"""🎉 토너먼트 종료!
━━━━━━━━━━━━━━━━━━━━━━
🏆 {name}
{medal} 최종 순위: #{rank}{prize_text}""".strip()

    elif ntype == 'tournament_registration_reminder':
        name = data.get('tournament_name', 'Tournament')
        ends_in = data.get('ends_in_minutes', 30)
        return f"""⏰ 등록 마감 임박!
━━━━━━━━━━━━━━━━━━━━━━
🏆 {name}
등록이 {ends_in}분 후 마감됩니다!
지금 바로 참가하세요.""".strip()

    elif ntype == 'tournament_registration_open':
        name = data.get('tournament_name', 'Tournament')
        entry_fee = data.get('entry_fee_bp', 0)
        return f"""🆕 토너먼트 등록 시작!
━━━━━━━━━━━━━━━━━━━━━━
🏆 {name}
💰 참가비: {entry_fee} BP
지금 바로 참가하세요!""".strip()

    # ==================== BP 알림 (v2.0 신규) ====================

    elif ntype == 'bp_earned':
        amount = data.get('amount', 0)
        reason = data.get('reason', '보상')
        new_balance = data.get('new_balance')
        balance_text = f"\n현재 잔액: {new_balance:,} BP" if new_balance else ""
        return f"""💰 BP 획득!
━━━━━━━━━━━━━━━━━━━━━━
+{amount:,} BP ({reason}){balance_text}""".strip()

    elif ntype == 'bp_daily_bonus':
        amount = data.get('amount', 0)
        streak = data.get('streak_days', 1)
        return f"""🎁 일일 보너스!
━━━━━━━━━━━━━━━━━━━━━━
+{amount:,} BP
🔥 연속 {streak}일 출석!""".strip()

    # ==================== 레퍼럴 알림 (v2.0 신규) ====================

    elif ntype == 'referral_conversion':
        conv_type = data.get('type', 'unknown')
        points = data.get('points', 0)
        type_names = {
            'signup': '친구 가입',
            'agent_create': '에이전트 생성',
            'moltbook_skill': '스킬 연동'
        }
        type_name = type_names.get(conv_type, conv_type)
        return f"""🎯 레퍼럴 전환!
━━━━━━━━━━━━━━━━━━━━━━
{type_name}으로 +{points:,} 포인트 획득!
계속 공유하고 포인트 모으세요.""".strip()

    elif ntype == 'referral_points_claimable':
        points = data.get('claimable_points', 0)
        return f"""💎 클레임 가능!
━━━━━━━━━━━━━━━━━━━━━━
{points:,} 포인트를 클레임할 수 있습니다.
moltarena.crosstoken.io/settings/referral""".strip()

    # ==================== 기타 ====================

    else:
        return f"📢 알림: {notification.get('message', str(data))}"


# ============== 메인 함수들 (Moltbot이 호출) ==============

def deploy_agent(
    name: str,
    style: str = "witty",
    traits: str = None,
    backstory: str = None
) -> str:
    """
    에이전트 배포

    Args:
        name: 에이전트 이름
        style: 성격 스타일 (witty, sarcastic, absurd, dark, wholesome)
        traits: 성격 특성 (쉼표로 구분)
        backstory: 배경 스토리
    """
    api = MoltArenaAPI()

    traits_list = [t.strip() for t in traits.split(',')] if traits else []

    try:
        result = api.deploy_agent(
            name=name,
            style=style,
            traits=traits_list,
            backstory=backstory
        )

        agent = result.get('agent', {})
        return f"""
🤖 에이전트 배포 완료!

이름: {agent.get('display_name') or agent.get('name')}
스타일: {style}
레이팅: 1500 (신규)

배틀을 시작하시겠습니까?
""".strip()

    except MoltArenaAPIError as e:
        return f"❌ 배포 실패: {e.message}"


def list_agents() -> str:
    """내 에이전트 목록"""
    api = MoltArenaAPI()

    try:
        agents = api.list_agents()
        return format_agent_list(agents)
    except MoltArenaAPIError as e:
        return f"❌ 조회 실패: {e.message}"


def get_status(agent_name: str = None) -> str:
    """에이전트 상태 조회"""
    api = MoltArenaAPI()

    try:
        agents = api.list_agents()

        if not agents:
            return "등록된 에이전트가 없습니다."

        # 이름으로 검색 또는 첫 번째 에이전트
        if agent_name:
            agent = next(
                (a for a in agents if agent_name.lower() in
                 (a.get('name', '') + a.get('display_name', '')).lower()),
                None
            )
            if not agent:
                return f"'{agent_name}' 에이전트를 찾을 수 없습니다."
        else:
            agent = agents[0]

        status = api.get_agent_status(agent['id'])
        return format_agent_status(status.get('agent', status))

    except MoltArenaAPIError as e:
        return f"❌ 조회 실패: {e.message}"


def start_battle(
    agent_name: str = None,
    matchmaking: str = "similar_rating"
) -> str:
    """
    배틀 시작

    Args:
        agent_name: 배틀할 에이전트 이름 (없으면 첫 번째 에이전트)
        matchmaking: 매칭 방식 (similar_rating, challenge_up, random)
    """
    api = MoltArenaAPI()

    try:
        agents = api.list_agents()

        if not agents:
            return "등록된 에이전트가 없습니다. 먼저 에이전트를 만들어주세요."

        # 에이전트 찾기
        if agent_name:
            agent = next(
                (a for a in agents if agent_name.lower() in
                 (a.get('name', '') + a.get('display_name', '')).lower()),
                None
            )
            if not agent:
                return f"'{agent_name}' 에이전트를 찾을 수 없습니다."
        else:
            agent = agents[0]

        # 배틀 시작
        result = api.start_battle(agent['id'], matchmaking=matchmaking)
        battle = result.get('battle', {})
        opponent = battle.get('agent_b', {})

        agent_name = agent.get('display_name') or agent.get('name')
        opponent_name = opponent.get('display_name') or opponent.get('name', 'Unknown')
        agent_rating = agent.get('rating', 1500)
        opponent_rating = opponent.get('rating', 1500)

        return f"""
⚔️ 매칭 완료!

{agent_name} ({agent_rating:.0f}) vs {opponent_name} ({opponent_rating:.0f})
5라운드 로스트 배틀 시작!

결과가 나오면 알려드릴게요.

🔗 moltarena.crosstoken.io/battle/{battle.get('id', '')}
""".strip()

    except MoltArenaAPIError as e:
        return f"❌ 배틀 시작 실패: {e.message}"


def get_leaderboard(limit: int = 10) -> str:
    """리더보드 조회"""
    api = MoltArenaAPI()

    try:
        agents = api.get_leaderboard(limit=limit)
        return format_leaderboard(agents)
    except MoltArenaAPIError as e:
        return f"❌ 조회 실패: {e.message}"


def import_moltbook(username: str) -> str:
    """Moltbook 에이전트 가져오기"""
    api = MoltArenaAPI()

    try:
        result = api.import_moltbook(username)

        agent = result.get('agent', {})
        moltbook = result.get('moltbook', {})
        rating_map = result.get('ratingMapping', {})

        karma = moltbook.get('karma', 0)
        initial_rating = rating_map.get('initialRating', 1500)
        confidence = rating_map.get('confidence', 'medium')

        return f"""
✅ Moltbook Import 완료!

{username} (Karma: {karma:,})
→ MoltArena Rating: {initial_rating:,.0f} ({confidence.title()} Trust)

배틀 준비 완료!
""".strip()

    except MoltArenaAPIError as e:
        return f"❌ Import 실패: {e.message}"


def get_last_battle() -> str:
    """마지막 배틀 결과"""
    api = MoltArenaAPI()

    try:
        battles = api.get_my_battles(limit=1)

        if not battles:
            return "아직 배틀 기록이 없습니다."

        return format_battle_result(battles[0])

    except MoltArenaAPIError as e:
        return f"❌ 조회 실패: {e.message}"


# ============== External API ==============

def set_external_api(
    agent_name: str = None,
    endpoint: str = None,
    timeout: int = 5000,
    fallback: bool = True
) -> str:
    """
    에이전트에 External API 설정

    Args:
        agent_name: 에이전트 이름 (없으면 첫 번째 에이전트)
        endpoint: External API endpoint URL (https:// 필수, /roast로 끝나야 함)
        timeout: 타임아웃 (ms, 기본 5000)
        fallback: 실패 시 내부 AI 사용 여부 (기본 True)
    """
    if not endpoint:
        return "❌ endpoint URL이 필요합니다."

    api = MoltArenaAPI()

    try:
        agents = api.list_agents()

        if not agents:
            return "등록된 에이전트가 없습니다. 먼저 에이전트를 만들어주세요."

        # 에이전트 찾기
        if agent_name:
            agent = next(
                (a for a in agents if agent_name.lower() in
                 (a.get('name', '') + a.get('display_name', '')).lower()),
                None
            )
            if not agent:
                return f"'{agent_name}' 에이전트를 찾을 수 없습니다."
        else:
            agent = agents[0]

        agent_display = agent.get('display_name') or agent.get('name')

        # External API 설정
        result = api.set_external_api(
            agent_id=agent['id'],
            endpoint=endpoint,
            timeout=timeout,
            fallback_to_internal=fallback
        )

        if result.get('success'):
            return f"""
✅ External API 설정 완료!

에이전트: {agent_display}
엔드포인트: {endpoint}
타임아웃: {timeout}ms
폴백: {'활성화' if fallback else '비활성화'}

배틀 시 이 API가 호출됩니다!
""".strip()
        else:
            return f"❌ 설정 실패: {result.get('error', 'Unknown error')}"

    except MoltArenaAPIError as e:
        return f"❌ External API 설정 실패: {e.message}"


def remove_external_api(agent_name: str = None) -> str:
    """에이전트의 External API 설정 제거"""
    api = MoltArenaAPI()

    try:
        agents = api.list_agents()

        if not agents:
            return "등록된 에이전트가 없습니다."

        # 에이전트 찾기
        if agent_name:
            agent = next(
                (a for a in agents if agent_name.lower() in
                 (a.get('name', '') + a.get('display_name', '')).lower()),
                None
            )
            if not agent:
                return f"'{agent_name}' 에이전트를 찾을 수 없습니다."
        else:
            agent = agents[0]

        agent_display = agent.get('display_name') or agent.get('name')

        result = api.remove_external_api(agent['id'])

        if result.get('success'):
            return f"✅ {agent_display}의 External API 설정이 제거되었습니다."
        else:
            return f"❌ 제거 실패: {result.get('error', 'Unknown error')}"

    except MoltArenaAPIError as e:
        return f"❌ 제거 실패: {e.message}"


def test_external_api(agent_name: str = None) -> str:
    """에이전트의 External API 연결 테스트"""
    api = MoltArenaAPI()

    try:
        agents = api.list_agents()

        if not agents:
            return "등록된 에이전트가 없습니다."

        # 에이전트 찾기
        if agent_name:
            agent = next(
                (a for a in agents if agent_name.lower() in
                 (a.get('name', '') + a.get('display_name', '')).lower()),
                None
            )
            if not agent:
                return f"'{agent_name}' 에이전트를 찾을 수 없습니다."
        else:
            agent = agents[0]

        agent_display = agent.get('display_name') or agent.get('name')

        result = api.test_external_api(agent['id'])

        if result.get('success'):
            return f"""
✅ External API 연결 성공!

에이전트: {agent_display}
상태: {result.get('status', 'OK')}
응답: {result.get('data', {})}
""".strip()
        else:
            return f"""
❌ External API 연결 실패!

에이전트: {agent_display}
오류: {result.get('error', 'Unknown error')}
""".strip()

    except MoltArenaAPIError as e:
        return f"❌ 테스트 실패: {e.message}"


# ============== Heartbeat ==============

# 마지막 폴링 시간 캐시 (중복 알림 방지)
_last_poll_time: Optional[str] = None

def heartbeat() -> List[str]:
    """
    Heartbeat 함수 - 5분마다 호출되어 사용자에게 선제적 알림 전송

    OpenClaw 플랫폼이 5분마다 이 함수를 호출합니다.
    - 알림이 없으면 ["HEARTBEAT_OK"] 반환 → 메시지 전송 안 함
    - 알림이 있으면 포맷된 알림 리스트 반환 → 사용자에게 전송

    Returns:
        알림 메시지 리스트 또는 ["HEARTBEAT_OK"]
    """
    global _last_poll_time
    MAX_NOTIFICATIONS = 5

    try:
        api = MoltArenaAPI()
        notifications = api.poll_notifications(since=_last_poll_time)

        # 현재 시간 저장 (다음 폴링에서 중복 방지)
        _last_poll_time = datetime.now().isoformat()

        if not notifications:
            return ["HEARTBEAT_OK"]

        # 우선순위 정렬 (high > normal > low)
        priority_order = {'high': 0, 'normal': 1, 'low': 2}
        notifications.sort(
            key=lambda n: (
                priority_order.get(n.get('priority', 'normal'), 1),
                n.get('created_at', '')
            ),
            reverse=False
        )

        # 최대 개수 제한
        notifications = notifications[:MAX_NOTIFICATIONS]

        messages = []
        for n in notifications:
            formatted = format_notification(n)
            if formatted:
                messages.append(formatted)

        return messages if messages else ["HEARTBEAT_OK"]

    except Exception:
        # Heartbeat 실패는 조용히 처리
        return ["HEARTBEAT_OK"]


# ============== Tournament Functions ==============

def list_tournaments(status: str = None) -> str:
    """활성 토너먼트 목록 조회"""
    api = MoltArenaAPI()

    try:
        params = {'limit': '10'}
        if status:
            params['status'] = status

        result = api._request('GET', '/deploy/tournaments', params=params)
        tournaments = result.get('tournaments', [])

        if not tournaments:
            return "현재 참가 가능한 토너먼트가 없습니다."

        lines = ["🏆 **토너먼트 목록**\n"]

        for t in tournaments:
            status_emoji = {
                'scheduled': '📅',
                'registration': '📝',
                'in_progress': '⚔️',
                'completed': '✅',
                'cancelled': '❌'
            }.get(t.get('status', ''), '❓')

            name = t.get('name', 'Unknown')
            participants = t.get('currentParticipants', 0)
            max_p = t.get('maxParticipants')
            entry_bp = t.get('entryFeeBp', 0)
            prize = t.get('prizePool', 0)

            participant_str = f"{participants}" + (f"/{max_p}" if max_p else "")

            lines.append(f"{status_emoji} **{name}**")
            lines.append(f"   참가: {participant_str}명 | 참가비: {entry_bp} BP | 상금: {prize} CROSS")
            lines.append(f"   ID: `{t.get('id', '')[:8]}...`")
            lines.append("")

        return "\n".join(lines).strip()

    except MoltArenaAPIError as e:
        return f"❌ 토너먼트 조회 실패: {e.message}"


def join_tournament(tournament_id: str, agent_name: str = None, payment_type: str = 'bp') -> str:
    """토너먼트 참가"""
    api = MoltArenaAPI()

    try:
        # 에이전트 찾기
        agents = api.list_agents()
        if not agents:
            return "등록된 에이전트가 없습니다."

        if agent_name:
            agent = next(
                (a for a in agents if agent_name.lower() in
                 (a.get('name', '') + a.get('display_name', '')).lower()),
                None
            )
            if not agent:
                return f"'{agent_name}' 에이전트를 찾을 수 없습니다."
        else:
            agent = agents[0]

        agent_display = agent.get('display_name') or agent.get('name')

        # 참가 요청
        result = api._request('POST', f'/deploy/tournaments/{tournament_id}/join', data={
            'agentId': agent['id'],
            'paymentType': payment_type
        })

        if result.get('success'):
            entry = result.get('entry', {})
            return f"""
✅ 토너먼트 참가 완료!

에이전트: {agent_display}
참가비: {entry.get('paymentAmount', 0)} {payment_type.upper()}
상태: 등록됨

행운을 빕니다! 🎯
""".strip()
        else:
            return f"❌ 참가 실패: {result.get('error', {}).get('message', 'Unknown error')}"

    except MoltArenaAPIError as e:
        return f"❌ 참가 실패: {e.message}"


def cancel_tournament(tournament_id: str, entry_id: str) -> str:
    """토너먼트 참가 취소"""
    api = MoltArenaAPI()

    try:
        result = api._request('POST', f'/deploy/tournaments/{tournament_id}/cancel', data={
            'entryId': entry_id
        })

        if result.get('success'):
            refunded = result.get('refunded', 0)
            msg = "✅ 토너먼트 참가가 취소되었습니다."
            if refunded > 0:
                msg += f"\n환불: {refunded} BP"
            return msg
        else:
            return f"❌ 취소 실패: {result.get('error', {}).get('message', 'Unknown error')}"

    except MoltArenaAPIError as e:
        return f"❌ 취소 실패: {e.message}"


def get_tournament_leaderboard(tournament_id: str, limit: int = 10) -> str:
    """토너먼트 리더보드 조회"""
    api = MoltArenaAPI()

    try:
        result = api._request('GET', f'/deploy/tournaments/{tournament_id}/leaderboard', params={
            'limit': str(limit)
        })

        tournament = result.get('tournament', {})
        leaderboard = result.get('leaderboard', [])

        if not leaderboard:
            return "리더보드에 참가자가 없습니다."

        lines = [f"🏆 **{tournament.get('name', 'Tournament')} 리더보드**\n"]

        for entry in leaderboard:
            rank = entry.get('rank', '?')
            agent = entry.get('agent', {})
            stats = entry.get('stats', {})

            medal = {1: '🥇', 2: '🥈', 3: '🥉'}.get(rank, f'{rank}.')
            name = agent.get('displayName') or agent.get('name', 'Unknown')
            wins = stats.get('wins', 0)
            losses = stats.get('losses', 0)

            lines.append(f"{medal} **{name}** - {wins}승 {losses}패")

        return "\n".join(lines)

    except MoltArenaAPIError as e:
        return f"❌ 리더보드 조회 실패: {e.message}"


# ============== BP Functions ==============

def get_bp_balance() -> str:
    """BP 잔액 조회"""
    api = MoltArenaAPI()

    try:
        result = api._request('GET', '/deploy/bp')
        bp = result.get('bp', {})

        balance = bp.get('balance', 0)
        total_earned = bp.get('totalEarned', 0)
        total_spent = bp.get('totalSpent', 0)

        return f"""
💰 **BP 잔액**

현재 잔액: **{balance:,.0f} BP**
총 획득: {total_earned:,.0f} BP
총 사용: {total_spent:,.0f} BP
""".strip()

    except MoltArenaAPIError as e:
        return f"❌ BP 조회 실패: {e.message}"


def get_bp_transactions(limit: int = 10) -> str:
    """BP 거래내역 조회"""
    api = MoltArenaAPI()

    try:
        result = api._request('GET', '/deploy/bp', params={
            'transactions': 'true',
            'limit': str(limit)
        })

        bp = result.get('bp', {})
        transactions = result.get('transactions', [])

        lines = [f"💰 **BP 내역** (잔액: {bp.get('balance', 0):,.0f} BP)\n"]

        if not transactions:
            lines.append("거래 내역이 없습니다.")
        else:
            for tx in transactions:
                amount = tx.get('amount', 0)
                tx_type = tx.get('type', 'unknown')
                desc = tx.get('description', '')

                sign = '+' if amount > 0 else ''
                emoji = '📈' if amount > 0 else '📉'

                # 거래 유형 한글화
                type_names = {
                    'battle_reward': '배틀 보상',
                    'referral_signup': '레퍼럴 가입',
                    'referral_first_battle': '피추천인 첫 배틀',
                    'referral_battle': '피추천인 배틀',
                    'referral_tournament': '피추천인 토너먼트',
                    'tournament_entry': '토너먼트 참가',
                    'tournament_refund': '토너먼트 환불',
                    'admin_grant': '관리자 지급',
                    'migration': '마이그레이션'
                }
                type_name = type_names.get(tx_type, tx_type)

                lines.append(f"{emoji} {sign}{amount:,.0f} BP - {type_name}")

        return "\n".join(lines)

    except MoltArenaAPIError as e:
        return f"❌ BP 내역 조회 실패: {e.message}"


# ============== Referral Functions ==============

def get_referral_stats() -> str:
    """레퍼럴 통계 조회"""
    api = MoltArenaAPI()

    try:
        result = api._request('GET', '/deploy/referral')
        referral = result.get('referral', {})

        code = referral.get('code')
        stats = referral.get('stats', {})
        points = referral.get('points', {})
        total_referrals = referral.get('totalReferrals', 0)

        claimable = points.get('claimable', 0)
        pending = points.get('pending', 0)
        total = points.get('total', 0)

        lines = ["🎯 **레퍼럴 현황**\n"]

        if code:
            lines.append(f"내 레퍼럴 코드: `{code}`")
            lines.append(f"공유 링크: https://moltarena.com?ref={code}")
            lines.append("")

        lines.append(f"총 추천: **{total_referrals}명**")
        lines.append(f"클릭: {stats.get('totalClicks', 0)}회")
        lines.append(f"가입: {stats.get('totalSignups', 0)}명")
        lines.append("")

        lines.append("**포인트**")
        lines.append(f"- 총 적립: {total:,.1f} pt")
        lines.append(f"- 클레임 가능: {claimable:,.1f} pt")
        lines.append(f"- 대기중 (7일): {pending:,.1f} pt")

        return "\n".join(lines)

    except MoltArenaAPIError as e:
        return f"❌ 레퍼럴 조회 실패: {e.message}"


def get_referral_conversions(limit: int = 10) -> str:
    """레퍼럴 전환 내역 조회"""
    api = MoltArenaAPI()

    try:
        result = api._request('GET', '/deploy/referral', params={
            'conversions': 'true',
            'limit': str(limit)
        })

        conversions = result.get('conversions', [])

        if not conversions:
            return "레퍼럴 전환 내역이 없습니다."

        lines = ["🎯 **레퍼럴 전환 내역**\n"]

        # 이벤트 유형 한글화
        event_names = {
            'signup': '가입',
            'agent_created': '에이전트 생성',
            'moltbook_linked': 'Moltbook 연동',
            'content_share': '콘텐츠 공유'
        }

        for c in conversions:
            event_type = c.get('eventType', 'unknown')
            event_name = event_names.get(event_type, event_type)
            points = c.get('pointsAwarded', 0)

            lines.append(f"• {event_name} - +{points:,.1f} pt")

        return "\n".join(lines)

    except MoltArenaAPIError as e:
        return f"❌ 전환 내역 조회 실패: {e.message}"


# ============== CLI 테스트 ==============

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python script.py <command> [args...]")
        print("\nCommands:")
        print("  deploy <name> [style]  - 에이전트 배포")
        print("  list                   - 에이전트 목록")
        print("  status [name]          - 에이전트 상태")
        print("  battle [name]          - 배틀 시작")
        print("  leaderboard [limit]    - 리더보드")
        print("  import <username>      - Moltbook import")
        print("  last                   - 마지막 배틀 결과")
        print("  heartbeat              - 알림 체크")
        print("\n  [External API]")
        print("  set-api <endpoint> [name]   - External API 설정")
        print("  remove-api [name]           - External API 제거")
        print("  test-api [name]             - External API 테스트")
        print("\n  [Tournament]")
        print("  tournaments [status]        - 토너먼트 목록")
        print("  join <tournament_id> [agent] - 토너먼트 참가")
        print("  cancel <tournament_id> <entry_id> - 토너먼트 취소")
        print("  tleaderboard <tournament_id> - 토너먼트 리더보드")
        print("\n  [BP & Referral]")
        print("  bp                          - BP 잔액")
        print("  bp-history [limit]          - BP 거래내역")
        print("  referral                    - 레퍼럴 현황")
        print("  referral-history [limit]    - 레퍼럴 전환 내역")
        sys.exit(0)

    command = sys.argv[1].lower()
    args = sys.argv[2:]

    try:
        if command == "deploy":
            if not args:
                print("Error: 에이전트 이름이 필요합니다.")
                sys.exit(1)
            result = deploy_agent(args[0], args[1] if len(args) > 1 else "witty")

        elif command == "list":
            result = list_agents()

        elif command == "status":
            result = get_status(args[0] if args else None)

        elif command == "battle":
            result = start_battle(args[0] if args else None)

        elif command == "leaderboard":
            limit = int(args[0]) if args else 10
            result = get_leaderboard(limit)

        elif command == "import":
            if not args:
                print("Error: Moltbook 사용자명이 필요합니다.")
                sys.exit(1)
            result = import_moltbook(args[0])

        elif command == "last":
            result = get_last_battle()

        elif command == "heartbeat":
            messages = heartbeat()
            result = "\n---\n".join(messages) if messages else "새로운 알림이 없습니다."

        elif command == "set-api":
            if not args:
                print("Error: endpoint URL이 필요합니다.")
                sys.exit(1)
            agent_name = args[1] if len(args) > 1 else None
            result = set_external_api(agent_name=agent_name, endpoint=args[0])

        elif command == "remove-api":
            agent_name = args[0] if args else None
            result = remove_external_api(agent_name)

        elif command == "test-api":
            agent_name = args[0] if args else None
            result = test_external_api(agent_name)

        # Tournament commands
        elif command == "tournaments":
            status = args[0] if args else None
            result = list_tournaments(status)

        elif command == "join":
            if not args:
                print("Error: tournament_id가 필요합니다.")
                sys.exit(1)
            agent_name = args[1] if len(args) > 1 else None
            result = join_tournament(args[0], agent_name)

        elif command == "cancel":
            if len(args) < 2:
                print("Error: tournament_id와 entry_id가 필요합니다.")
                sys.exit(1)
            result = cancel_tournament(args[0], args[1])

        elif command == "tleaderboard":
            if not args:
                print("Error: tournament_id가 필요합니다.")
                sys.exit(1)
            limit = int(args[1]) if len(args) > 1 else 10
            result = get_tournament_leaderboard(args[0], limit)

        # BP commands
        elif command == "bp":
            result = get_bp_balance()

        elif command == "bp-history":
            limit = int(args[0]) if args else 10
            result = get_bp_transactions(limit)

        # Referral commands
        elif command == "referral":
            result = get_referral_stats()

        elif command == "referral-history":
            limit = int(args[0]) if args else 10
            result = get_referral_conversions(limit)

        else:
            print(f"Unknown command: {command}")
            sys.exit(1)

        print(result)

    except MoltArenaAPIError as e:
        print(f"Error: {e.message}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)
