# hantubot_prod/hantubot/reporting/report.py
import json
import os
from datetime import datetime
from typing import Dict, List, Any
import pandas as pd

from .logger import get_logger
from .notifier import Notifier
from .study_db import get_study_db # DB 연동 추가

logger = get_logger(__name__)

class ReportGenerator:
    """
    거래 로그를 분석하여 일일 리포트를 생성하고 알림을 보냅니다.
    """
    def __init__(self, config: Dict, notifier: Notifier):
        self.config = config
        self.notifier = notifier
        
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        self.log_dir = os.path.join(base_dir, config.get('logging', {}).get('directory', 'logs'))
        self.report_dir = os.path.join(base_dir, 'reports')
        os.makedirs(self.report_dir, exist_ok=True)

    def _read_log_file(self, file_path: str) -> List[Dict]:
        """JSONL 파일을 읽어 딕셔너리 리스트로 반환합니다."""
        if not os.path.exists(file_path):
            logger.warning(f"Log file not found: {file_path}")
            return []
        
        records = []
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.error(f"Failed to decode JSON from line: {line.strip()}")
        return records

    def generate_daily_report(self):
        """
        오늘 날짜의 거래 로그를 읽어 일일 리포트를 생성합니다.
        """
        today_str = datetime.now().strftime('%Y-%m-%d')
        trades_log_path = os.path.join(self.log_dir, f"trades_{today_str}.jsonl")
        
        trades_data = self._read_log_file(trades_log_path)
        if not trades_data:
            logger.info("No trade data for today. Skipping report generation.")
            self.notifier.send_alert("금일 거래 내역이 없어 리포트를 생성하지 않았습니다.", level='info')
            return

        df = pd.DataFrame(trades_data)
        
        # --- 분석 로직 ---
        fills = df[df['event_type'] == 'FILL'].copy()
        if fills.empty:
            summary_text = "금일 체결된 거래가 없습니다."
        else:
            # Pandas의 숫자 타입을 float으로 통일
            fills['filled_quantity'] = pd.to_numeric(fills['filled_quantity'], errors='coerce')
            fills['fill_price'] = pd.to_numeric(fills['fill_price'], errors='coerce')
            fills['pnl_krw'] = pd.to_numeric(fills['pnl_krw'], errors='coerce').fillna(0) # pnl_krw 추가

            buys = fills[fills['side'] == 'buy']
            sells = fills[fills['side'] == 'sell']
            
            total_buy_value = (buys['filled_quantity'] * buys['fill_price']).sum()
            total_sell_value = (sells['filled_quantity'] * sells['fill_price']).sum()
            total_realized_pnl_krw = sells['pnl_krw'].sum() # 실현 손익 합계
            
            num_buy_trades = len(buys)
            num_sell_trades = len(sells)
            
            summary_text = (
                f"- 총 체결 건수: **{len(fills)}** 건\n"
                f"- 매수 체결: {num_buy_trades} 건 (총 {total_buy_value:,.0f} 원)\n"
                f"- 매도 체결: {num_sell_trades} 건 (총 {total_sell_value:,.0f} 원)\n"
                f"- 실현 손익: **{total_realized_pnl_krw:,.0f}** 원\n" # PnL 추가
            )

        # --- 리포트 생성 ---
        report_md = f"""
# Hantubot 일일 리포트 ({today_str})

##  거래 요약

{summary_text}

## 전체 체결 내역
"""
        if not fills.empty:
            # 리포트에 포함할 컬럼 선택 및 순서 지정
            display_columns = ['timestamp', 'symbol', 'side', 'filled_quantity', 'fill_price', 'pnl_krw', 'order_id'] # pnl_krw 추가
            report_md += fills[display_columns].to_markdown(index=False)
        else:
            report_md += "\n체결 내역 없음."

        # 리포트 파일 저장
        report_file_path = os.path.join(self.report_dir, f"report_{today_str}.md")
        with open(report_file_path, 'w', encoding='utf-8') as f:
            f.write(report_md)
        
        logger.info(f"Daily report saved to {report_file_path}")

        # --- [추가] 전일 후보 성과 요약 (목표 A-3) ---
        closing_summary_fields = []
        try:
            db = get_study_db()
            # 오늘 평가된 결과 조회 (eval_date = today_str)
            # closing_candidate_results 테이블에서 조회해야 함
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT r.*, c.name 
                    FROM closing_candidate_results r
                    JOIN closing_candidates c ON r.candidate_id = c.id
                    WHERE r.eval_date = ?
                    ORDER BY c.rank ASC
                """, (today_str,))
                results = [dict(row) for row in cursor.fetchall()]
            
            if results:
                summary_text += "\n\n**🐫 전일 종가매매 후보 성과**\n"
                for res in results:
                    name = res.get('name', res['ticker'])
                    open_ret = res.get('next_open_return_pct', 0)
                    close_ret = res.get('next_close_return_pct', 0)
                    mfe = res.get('next_day_mfe_pct', 0)
                    
                    emoji = "🔴" if close_ret > 0 else "🔵"
                    summary_text += f"- {name}: 시가 {open_ret:+.2f}% / 종가 {close_ret:+.2f}% (최대 {mfe:+.2f}%)\n"
                    
                    closing_summary_fields.append({
                        "name": f"{emoji} {name}",
                        "value": f"시가: {open_ret:+.2f}% | 종가: {close_ret:+.2f}%\n최대수익: {mfe:+.2f}%",
                        "inline": True
                    })
            else:
                summary_text += "\n\n(전일 종가매매 후보 평가 데이터 없음)"

        except Exception as e:
            logger.error(f"성과 리포트 추가 실패: {e}")

        # --- 알림 전송 ---
        discord_embed = {
            "title": f"📈 일일 리포트 ({today_str})",
            "description": summary_text, 
            "color": 5814783, # Blue
            "fields": closing_summary_fields, # 필드 추가
            "footer": {"text": "상세 내용은 저장된 마크다운 리포트를 확인하세요."}
        }
        self.notifier.send_alert(f"일일 리포트가 생성되었습니다.", level='info', embed=discord_embed)
