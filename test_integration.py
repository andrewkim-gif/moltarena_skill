#!/usr/bin/env python3
"""
Moltbot Skill → Agent Arena API 통합 테스트

사용법:
  1. API Key 발급: https://agentarena-theta.vercel.app/settings/api
  2. 환경변수 설정: export PAWNED_API_KEY=pk_live_xxxxx
  3. 테스트 실행: python test_integration.py

테스트 항목:
  - API Key 인증
  - 에이전트 생성/조회
  - 배틀 시작
  - 리더보드 조회
"""

import os
import sys
import json
from datetime import datetime

# API URL 설정 (로컬 테스트 시 변경)
API_URL = os.getenv('PAWNED_API_URL', 'https://agentarena-theta.vercel.app/api')
API_KEY = os.getenv('PAWNED_API_KEY')

# 색상 출력
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}  {text}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}")

def print_pass(text):
    print(f"  {Colors.GREEN}✅ PASS{Colors.RESET}: {text}")

def print_fail(text, error=None):
    print(f"  {Colors.RED}❌ FAIL{Colors.RESET}: {text}")
    if error:
        print(f"         {Colors.YELLOW}Error: {error}{Colors.RESET}")

def print_info(text):
    print(f"  {Colors.YELLOW}ℹ️  INFO{Colors.RESET}: {text}")

def print_skip(text):
    print(f"  {Colors.YELLOW}⏭️  SKIP{Colors.RESET}: {text}")


def test_environment():
    """환경 변수 테스트"""
    print_header("1. 환경 변수 검증")

    if not API_KEY:
        print_fail("PAWNED_API_KEY 환경변수가 설정되지 않음")
        print_info("발급 방법: https://agentarena-theta.vercel.app/settings/api")
        return False

    if not API_KEY.startswith('pk_live_'):
        print_fail(f"API Key 형식 오류: {API_KEY[:12]}...")
        print_info("올바른 형식: pk_live_xxxxxxxx")
        return False

    print_pass(f"API Key 확인됨: {API_KEY[:12]}...")
    print_pass(f"API URL: {API_URL}")
    return True


def test_api_connection():
    """API 연결 테스트"""
    print_header("2. API 연결 테스트")

    try:
        import requests
    except ImportError:
        print_fail("requests 라이브러리가 설치되지 않음")
        print_info("설치: pip install requests")
        return False

    try:
        # 간단한 인증 테스트 (에이전트 목록 조회)
        response = requests.get(
            f"{API_URL}/deploy/list",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json"
            },
            timeout=10
        )

        if response.status_code == 200:
            print_pass("API 연결 성공")
            print_pass("인증 토큰 유효")
            return True
        elif response.status_code == 401:
            print_fail("인증 실패", response.json().get('error', {}).get('message'))
            return False
        elif response.status_code == 429:
            print_fail("Rate Limit 초과", "잠시 후 다시 시도하세요")
            return False
        else:
            print_fail(f"HTTP {response.status_code}", response.text[:100])
            return False

    except requests.exceptions.ConnectionError:
        print_fail("API 서버 연결 불가", f"{API_URL}")
        return False
    except requests.exceptions.Timeout:
        print_fail("요청 시간 초과")
        return False


def test_agent_list():
    """에이전트 목록 조회 테스트"""
    print_header("3. 에이전트 목록 조회")

    import requests

    response = requests.get(
        f"{API_URL}/deploy/list",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        },
        timeout=10
    )

    if response.status_code != 200:
        print_fail("조회 실패", response.text[:100])
        return None

    data = response.json()
    agents = data.get('agents', [])

    print_pass(f"조회 성공: {len(agents)}개 에이전트")

    for i, agent in enumerate(agents[:5], 1):
        name = agent.get('display_name') or agent.get('name', 'Unknown')
        rating = agent.get('rating', 1500)
        print_info(f"  {i}. {name} (Rating: {rating:.0f})")

    if len(agents) > 5:
        print_info(f"  ... 외 {len(agents) - 5}개")

    return agents


def test_agent_deploy(test_mode=True):
    """에이전트 배포 테스트"""
    print_header("4. 에이전트 배포 테스트")

    if test_mode:
        print_skip("테스트 모드에서는 실제 배포하지 않음")
        print_info("실제 배포 테스트: python test_integration.py --deploy")
        return True

    import requests

    # 테스트용 에이전트 이름 (중복 방지)
    test_name = f"TestBot_{datetime.now().strftime('%H%M%S')}"

    response = requests.post(
        f"{API_URL}/deploy/agent",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "name": test_name,
            "displayName": f"Test Bot {datetime.now().strftime('%H:%M:%S')}",
            "personality": {
                "style": "witty",
                "traits": ["test", "integration"],
                "backstory": "Integration test agent"
            }
        },
        timeout=30
    )

    if response.status_code == 201:
        data = response.json()
        agent = data.get('agent', {})
        print_pass(f"배포 성공: {agent.get('name')}")
        print_info(f"Agent ID: {agent.get('id')}")
        print_info(f"Rating: {agent.get('rating', 1500)}")
        return agent
    elif response.status_code == 409:
        print_fail("이름 중복", "다른 이름으로 시도하세요")
        return None
    else:
        print_fail(f"배포 실패 (HTTP {response.status_code})", response.text[:200])
        return None


def test_leaderboard():
    """리더보드 조회 테스트"""
    print_header("5. 리더보드 조회")

    import requests

    response = requests.get(
        f"{API_URL}/leaderboard?limit=5",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        },
        timeout=10
    )

    if response.status_code != 200:
        print_fail("조회 실패", response.text[:100])
        return False

    data = response.json()
    agents = data.get('agents', [])

    print_pass(f"조회 성공: Top {len(agents)}")

    medals = ['🥇', '🥈', '🥉', '4.', '5.']
    for i, agent in enumerate(agents[:5]):
        name = agent.get('display_name') or agent.get('name', 'Unknown')
        rating = agent.get('rating', 0)
        print_info(f"  {medals[i]} {name} - {rating:,.0f}")

    return True


def test_script_import():
    """script.py import 테스트"""
    print_header("6. Moltbot Script Import")

    try:
        from script import PawnedAPI, deploy_agent, list_agents, get_leaderboard
        print_pass("script.py import 성공")
        print_pass("PawnedAPI 클래스 확인")
        print_pass("deploy_agent 함수 확인")
        print_pass("list_agents 함수 확인")
        print_pass("get_leaderboard 함수 확인")
        return True
    except ImportError as e:
        print_fail(f"import 실패: {e}")
        return False


def test_script_functions():
    """script.py 함수 테스트"""
    print_header("7. Script 함수 테스트")

    try:
        from script import PawnedAPI

        api = PawnedAPI()
        print_pass("PawnedAPI 인스턴스 생성")

        # 에이전트 목록
        agents = api.list_agents()
        print_pass(f"list_agents(): {len(agents)}개 반환")

        # 리더보드
        leaderboard = api.get_leaderboard(limit=3)
        print_pass(f"get_leaderboard(): {len(leaderboard)}개 반환")

        return True

    except Exception as e:
        print_fail(f"함수 테스트 실패: {e}")
        return False


def main():
    """메인 테스트 실행"""
    print(f"\n{Colors.BOLD}🧪 Moltbot Skill → Agent Arena 통합 테스트{Colors.RESET}")
    print(f"   시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   API URL: {API_URL}")

    results = {
        'total': 0,
        'passed': 0,
        'failed': 0,
        'skipped': 0
    }

    # 실제 배포 테스트 여부
    deploy_test = '--deploy' in sys.argv

    # 테스트 실행
    tests = [
        ('환경 변수', test_environment),
        ('API 연결', test_api_connection),
        ('에이전트 목록', test_agent_list),
        ('리더보드', test_leaderboard),
        ('Script Import', test_script_import),
        ('Script 함수', test_script_functions),
    ]

    for name, test_func in tests:
        results['total'] += 1
        try:
            result = test_func()
            if result is None or result is False:
                results['failed'] += 1
                if name == '환경 변수':
                    # 환경 변수 실패 시 중단
                    break
            else:
                results['passed'] += 1
        except Exception as e:
            print_fail(f"예외 발생: {e}")
            results['failed'] += 1

    # 에이전트 배포 테스트 (선택적)
    results['total'] += 1
    if deploy_test:
        if test_agent_deploy(test_mode=False):
            results['passed'] += 1
        else:
            results['failed'] += 1
    else:
        test_agent_deploy(test_mode=True)
        results['skipped'] += 1

    # 결과 요약
    print_header("테스트 결과 요약")
    print(f"  총 테스트: {results['total']}")
    print(f"  {Colors.GREEN}통과: {results['passed']}{Colors.RESET}")
    print(f"  {Colors.RED}실패: {results['failed']}{Colors.RESET}")
    print(f"  {Colors.YELLOW}스킵: {results['skipped']}{Colors.RESET}")

    if results['failed'] == 0:
        print(f"\n{Colors.GREEN}{Colors.BOLD}✅ 모든 테스트 통과!{Colors.RESET}")
        print(f"   Moltbot 스킬 통합 준비 완료")
        return 0
    else:
        print(f"\n{Colors.RED}{Colors.BOLD}❌ 일부 테스트 실패{Colors.RESET}")
        print(f"   위 오류를 확인하고 수정하세요")
        return 1


if __name__ == "__main__":
    sys.exit(main())
