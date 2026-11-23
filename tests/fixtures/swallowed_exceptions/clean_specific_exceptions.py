def handle_specific():
    try:
        int("abc")
    except ValueError:
        pass

    try:
        d = {}
        _ = d["key"]
    except KeyError:
        ...

    try:
        open("missing.txt")
    except (FileNotFoundError, PermissionError):
        pass

    try:
        raise ExceptionGroup("group", [ValueError()])
    except* ValueError:
        pass
