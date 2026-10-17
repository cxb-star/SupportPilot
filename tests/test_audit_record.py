import pytest
from unittest.mock import patch
from agent.tools import create_ticket, transition_ticket
from store.audit import record


def _make_db(tmp_path):
    db = tmp_path / 'audit_test.db'
    create_ticket(db, 'u1', 'test', intent='refund')
    return db


class TestCreateTicketAudit:
    def test_record_called_with_correct_fields(self, tmp_path):
        db = _make_db(tmp_path)
        with patch('agent.tools.record') as mock_record:
            t = create_ticket(db, 'u1', '退款问题', intent='refund')
            assert mock_record.called
            call_args = mock_record.call_args[0][0]
            assert call_args['event'] == 'ticket_created'
            assert call_args['ticket_no'].startswith('TICKET-')
            assert call_args['user_id'] == 'u1'
            assert call_args['intent'] == 'refund'
            assert call_args['priority'] == 'normal'
            assert call_args['team'] == 'aftersales'
            assert t['priority'] == 'normal'
            assert t['team'] == 'aftersales'

    def test_record_not_blocked_by_mock(self, tmp_path):
        db = tmp_path / 'audit_test.db'
        with patch('agent.tools.record') as mock_record:
            t = create_ticket(db, 'u2', '任意问题')
            assert mock_record.called
            assert t['ticket_no'].startswith('TICKET-')


class TestTransitionTicketAudit:
    def test_record_called_with_from_to(self, tmp_path):
        db = _make_db(tmp_path)
        ticket_no = str(create_ticket(db, 'u1', 'test', intent='refund')['ticket_no'])
        with patch('agent.tools.record') as mock_record:
            t = transition_ticket(db, ticket_no, 'in_progress', assignee='admin')
            assert mock_record.called
            call_args = mock_record.call_args[0][0]
            assert call_args['event'] == 'ticket_transition'
            assert call_args['ticket_no'] == ticket_no
            assert call_args['from'] == 'open'
            assert call_args['to'] == 'in_progress'
            assert call_args['assignee'] == 'admin'
            assert t['status'] == 'in_progress'
            assert t['assigned_to'] == 'admin'

    def test_record_not_called_on_illegal_transition(self, tmp_path):
        db = _make_db(tmp_path)
        ticket_no = str(create_ticket(db, 'u1', 'test', intent='refund')['ticket_no'])
        with patch('agent.tools.record') as mock_record:
            with pytest.raises(ValueError):
                transition_ticket(db, ticket_no, 'open')
            assert not mock_record.called

    def test_record_not_called_on_missing_ticket(self, tmp_path):
        with patch('agent.tools.record') as mock_record:
            with pytest.raises(ValueError):
                transition_ticket(tmp_path / 'x.db', 'NONEXIST', 'closed')
            assert not mock_record.called


class TestPriorityFallbackAudit:
    def test_fallback_priority_and_team_recorded(self, tmp_path):
        db = tmp_path / 'audit_test.db'
        with patch('agent.tools.record') as mock_record:
            t = create_ticket(db, 'u3', '破损问题', intent='compensate')
            call_args = mock_record.call_args[0][0]
            assert call_args['priority'] == 'urgent'
            assert call_args['team'] == 'quality'
            assert t['priority'] == 'urgent'
            assert t['team'] == 'quality'

class TestAuditContextPropagation:
    def test_session_id_propagated_in_create_ticket(self, tmp_path):
        db = tmp_path / 'audit_test.db'
        with patch('agent.tools.record') as mock_record:
            t = create_ticket(db, 'u5', '会话问题', intent='refund', session_id='sess-abc')
            assert mock_record.called
            call_args = mock_record.call_args[0][0]
            assert call_args['session_id'] == 'sess-abc'

    def test_user_id_propagated_in_transition_ticket(self, tmp_path):
        db = tmp_path / 'audit_test.db'
        t = create_ticket(db, 'u1', 'test', intent='refund')
        ticket_no = t['ticket_no']
        with patch('agent.tools.record') as mock_record:
            transition_ticket(db, ticket_no, 'in_progress', assignee='admin', user_id='supervisor-1')
            call_args = mock_record.call_args[0][0]
            assert call_args['user_id'] == 'supervisor-1'

    def test_session_id_absent_when_not_provided(self, tmp_path):
        db = tmp_path / 'audit_test.db'
        with patch('agent.tools.record') as mock_record:
            create_ticket(db, 'u6', 'default session', intent='promo')
            call_args = mock_record.call_args[0][0]
            assert 'session_id' not in call_args

    def test_user_id_absent_when_not_provided(self, tmp_path):
        db = tmp_path / 'audit_test.db'
        t = create_ticket(db, 'u1', 'test', intent='refund')
        ticket_no = t['ticket_no']
        with patch('agent.tools.record') as mock_record:
            transition_ticket(db, ticket_no, 'closed')
            call_args = mock_record.call_args[0][0]
            assert 'user_id' not in call_args
