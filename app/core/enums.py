from enum import Enum

class InternalOrderStatus(str, Enum):
    REQUESTED = "REQUESTED"          # 우리 서버가 주문 요청 기록
    SUBMITTED = "SUBMITTED"          # Alpaca 제출 성공
    ACCEPTED = "ACCEPTED"            # Alpaca accepted
    PENDING = "PENDING"              # pending_new / new / 기타 진행중
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"                # API 예외 등