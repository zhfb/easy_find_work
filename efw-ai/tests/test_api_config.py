def test_config_put_get(client):
    r = client.put("/api/config", json={"key": "model", "value": "deepseek-v4-flash"})
    assert r.status_code == 200
    r2 = client.get("/api/config")
    assert r2.json()["model"] == "deepseek-v4-flash"


def test_profile_put_get(client):
    body = {"skills": "Linux,K8s", "experience_years": 3,
            "expected_salary_min": 15, "expected_salary_max": 25,
            "target_city": "武汉", "intention": "云原生方向", "resume_summary": ""}
    assert client.put("/api/profile", json=body).status_code == 200
    got = client.get("/api/profile").json()
    assert got["skills"] == "Linux,K8s"
