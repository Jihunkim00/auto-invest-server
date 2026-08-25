# Auto Invest Mandatory Regression Policy

For any change touching:

- scheduler
- automation profile
- risk
- sizing
- order execution
- lifecycle
- position management

the task is incomplete unless all of the following pass:

1. app/tests/integration/test_kis_automation_scheduler_replay.py
2. app/tests/integration/test_kis_automation_full_lifecycle_replay.py
3. full backend pytest
4. python -m compileall app
5. git diff --check

Do not weaken:
- min entry score >= 65
- possible-order freshness <= 10 sec
- cash-only
- max positions
- duplicate/reservation/idempotency
- daily trade cap
- market session/cutoff
- TP/SL
- execution authority

Tests must use isolated DB and FakeBroker/FakeKisClient only.
No real KIS submit is allowed in tests.