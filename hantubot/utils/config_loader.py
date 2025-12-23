# hantubot_prod/hantubot/utils/config_loader.py
import os
import yaml
import re

def load_config_with_env(config_path: str) -> dict:
    """
    YAML 설정 파일을 로드하면서 ${VAR} 또는 $VAR 형태의 환경 변수를 확장합니다.
    예: app_key: ${KIS_APP_KEY} -> KIS_APP_KEY 환경 변수의 값으로 대체됩니다.
    """
    # ${VAR} 또는 $VAR 형식의 패턴을 찾습니다.
    env_var_pattern = re.compile(r'\$\{(\w+)\}|\$(\w+)')

    def expand_vars(match):
        # 매칭된 그룹 중 None이 아닌 첫 번째 그룹 (변수 이름)을 찾습니다.
        var_name = next(g for g in match.groups() if g is not None)
        return os.getenv(var_name, '') # 환경 변수 값을 반환, 없으면 빈 문자열

    with open(config_path, 'r', encoding='utf-8') as f:
        config_str = f.read()
    
    expanded_config_str = env_var_pattern.sub(expand_vars, config_str)
    return yaml.safe_load(expanded_config_str)
