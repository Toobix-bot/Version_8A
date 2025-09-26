from echo_bridge.main import settings
print('DB_PATH:', settings.db_path)
print('EXISTS:', settings.db_path.exists())
print('ABS:', settings.db_path.resolve())
