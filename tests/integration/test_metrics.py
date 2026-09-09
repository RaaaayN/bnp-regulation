def test_prometheus_metrics_are_exposed(client) -> None:
    client.get("/health")

    response = client.get("/metrics")

    assert response.status_code == 200
    assert "ria_http_requests_total" in response.text
    assert 'path="/health"' in response.text
