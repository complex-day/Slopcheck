def process_data():
    # 1. Bare except: pass
    try:
        raw = open("data.txt").read()
    except:
        pass

    # 2. except Exception as e: print(e)
    try:
        val = int(raw)
    except Exception as e:
        print(e)

    # 3. except* Exception: pass
    try:
        val = float(raw)
    except* Exception:
        pass

    # 4. comment-plus-pass
    try:
        return val * 2
    except BaseException:
        # Silently ignore failure here
        pass
