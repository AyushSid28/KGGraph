from api import fetch_user


def app():
    user = fetch_user()
    return user["name"]
