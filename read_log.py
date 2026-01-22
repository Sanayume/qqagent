
try:
    with open('install_log.txt', 'r', encoding='utf-16') as f:
        print(f.read())
except Exception as e:
    print(f"UTF-16 failed: {e}")
    try:
        with open('install_log.txt', 'r', encoding='utf-8', errors='replace') as f:
            print(f.read())
    except Exception as e2:
        print(f"UTF-8 failed: {e2}")
