import pytest


@pytest.mark.asyncio
async def test_register_login_and_me(anonymous_client):
    payload = {"full_name": "Ada Lovelace", "email": "ada@example.com", "password": "password123"}
    registered = await anonymous_client.post("/api/v1/auth/register", json=payload)
    assert registered.status_code == 201
    body = registered.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == payload["email"]

    logged_in = await anonymous_client.post(
        "/api/v1/auth/login", json={"email": payload["email"], "password": payload["password"]}
    )
    assert logged_in.status_code == 200
    anonymous_client.headers["Authorization"] = f"Bearer {logged_in.json()['access_token']}"
    me = await anonymous_client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["full_name"] == payload["full_name"]


@pytest.mark.asyncio
async def test_auth_rejects_missing_and_wrong_credentials(anonymous_client):
    assert (await anonymous_client.get("/api/v1/auth/me")).status_code == 401
    await anonymous_client.post(
        "/api/v1/auth/register",
        json={"full_name": "User", "email": "user@example.com", "password": "password123"},
    )
    response = await anonymous_client.post(
        "/api/v1/auth/login", json={"email": "user@example.com", "password": "wrongpass"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_jobs_are_scoped_to_current_user(client, anonymous_client, create_job):
    job_id = (await create_job([{"name": "Learner", "email": "learner@example.com", "course_name": "Course", "completion_date": "2024-01-01"}])).json()["job_id"]
    await anonymous_client.post(
        "/api/v1/auth/register",
        json={"full_name": "Other User", "email": "other@example.com", "password": "password123"},
    )
    token = (await anonymous_client.post(
        "/api/v1/auth/login", json={"email": "other@example.com", "password": "password123"}
    )).json()["access_token"]
    anonymous_client.headers["Authorization"] = f"Bearer {token}"
    assert (await anonymous_client.get("/api/v1/jobs")).json()["jobs"] == []
    assert (await anonymous_client.get(f"/api/v1/jobs/{job_id}")).status_code == 403