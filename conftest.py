import pytest
from django.contrib.auth.models import User, Group


@pytest.fixture
def admin_user(db):
    user = User.objects.create_superuser(
        username="admin_test",
        email="admin@test.com",
        password="testpass123",
    )
    return user


@pytest.fixture
def normal_user(db):
    user = User.objects.create_user(
        username="user_test",
        email="user@test.com",
        password="testpass123",
    )
    return user


@pytest.fixture
def provider_user(db):
    provider_group, _ = Group.objects.get_or_create(name="provider")
    user = User.objects.create_user(
        username="provider_test",
        email="provider@test.com",
        password="testpass123",
    )
    user.groups.add(provider_group)
    return user


@pytest.fixture
def client_logged_in(client, normal_user):
    client.login(username="user_test", password="testpass123")
    return client


@pytest.fixture
def admin_client_logged_in(client, admin_user):
    client.login(username="admin_test", password="testpass123")
    return client
