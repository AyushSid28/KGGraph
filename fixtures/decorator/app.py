def login_required(fn):
    return fn


@login_required
def view():
    return 1
