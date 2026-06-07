def test_link_not_found_is_service_error():
    from services.exceptions import LinkNotFound, ServiceError
    assert issubclass(LinkNotFound, ServiceError)


def test_invalid_link_transition_carries_from_to():
    from services.exceptions import InvalidLinkTransition
    exc = InvalidLinkTransition(from_status="done", to_status="in_work")
    assert exc.from_status == "done"
    assert exc.to_status == "in_work"
    assert "done" in str(exc) and "in_work" in str(exc)


def test_executor_api_rejected_is_service_error():
    from services.exceptions import ExecutorAPIError, ExecutorAPIRejected, ServiceError
    assert issubclass(ExecutorAPIError, ServiceError)
    assert issubclass(ExecutorAPIRejected, ExecutorAPIError)
