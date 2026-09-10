import json


def test_demo_serves_interactive_portfolio(client) -> None:
    response = client.get("/demo")

    assert response.status_code == 200
    assert "RegLens" in response.text
    assert "Run complete analysis" in response.text
    assert 'src="/static/demo.js"' in response.text
    assert 'href="/static/demo.css"' in response.text


def test_root_opens_demo(client) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "Regulatory change analysis" in response.text


def test_demo_static_assets_are_served(client) -> None:
    script = client.get("/static/demo.js")
    stylesheet = client.get("/static/demo.css")

    assert script.status_code == 200
    assert "/v1/changes/compare" in script.text
    assert "/v1/impacts/analyze" in script.text
    assert stylesheet.status_code == 200
    assert "architecture-flow" in stylesheet.text


def test_demo_metrics_loads_generated_report(client, tmp_path, monkeypatch) -> None:
    report = tmp_path / "portfolio-metrics.json"
    report.write_text(json.dumps({"summary": {"retrieval": {"recall_at_k": 0.9}}}))
    monkeypatch.setenv("RIA_METRICS_REPORT", str(report))

    response = client.get("/demo/metrics")

    assert response.status_code == 200
    assert response.json() == {
        "available": True,
        "metrics": {"summary": {"retrieval": {"recall_at_k": 0.9}}},
        "source": "portfolio-metrics.json",
    }
