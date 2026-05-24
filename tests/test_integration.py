from sqlalchemy import text


def test_migrations_at_head(migrated_db):
    assert migrated_db.db.name.startswith("slm_")


def test_health_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_db_session_from_app(client, run_in_app_loop):
    factory = client.app.state.session_factory

    async def _query():
        async with factory() as session:
            result = await session.execute(text("SELECT 1"))
            return result.scalar_one()

    assert run_in_app_loop(_query) == 1


def test_me_authenticated(client, auth_headers):
    response = client.get("/api/v1/me", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == {"user_id": "test-user-123"}


def test_me_missing_token(client):
    response = client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.json() == {"detail": "Missing bearer token"}


def test_me_bad_token(client):
    response = client.get(
        "/api/v1/me",
        headers={"Authorization": "Bearer not-a-valid-jwt"},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid token"}
