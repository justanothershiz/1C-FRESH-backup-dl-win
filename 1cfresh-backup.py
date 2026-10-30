# -*- coding: utf-8 -*-
import urllib.request
import urllib.error
import json
import time
import os
import re
import shutil
import subprocess
from datetime import datetime  # Для работы с датами

# --- НАСТРОЙКИ ---
# Одна строка - один аккаунт: логин, пароль, ID АБОНЕНТА (не аккаунта пользователя), Имя (для различения); не забываем запятую
# ID баз - опционально во вложенном массиве
# Допустимый ввод:
# ["login", "password", "ID абонента", "Произвольное имя", ["ID базы 1", "ID базы 2", "ID базы 3"]],
# ["login", "password", "ID абонента", "Произвольное имя", ["ID базы 1"]],
# ["login", "password", "ID абонента", "Произвольное имя"],
accounts_array = [
    ["", "", "", "", ["", "", ""]],
    ["", "", "", "", [""]],
    ["", "", "", ""],
]
fresh_server = "https://1cfresh.com"
folder_path = r"" # Путь папки с бэкапами
exe_7za = r"" # Путь к 7za.exe, оставить пустым для отключения
cooldown_time = 5


# Начинаем обрабатывать массив
def account_init(accounts_array):
    global error_count
    while accounts_array:
        account = accounts_array.pop(0)
        fresh_login, fresh_password, fresh_id, fresh_name = [item.strip() for item in account[:4]]
        is_frid_invalid = (
            fresh_id is None or 
            str(fresh_id) == "" or 
            not str(fresh_id).isdigit()
        )
        if is_frid_invalid:
            smart_print(f"\n        ! Клиент: {fresh_name}: Определение ID абонента пустое или содержит недопустимые символы")
            error_count += 1
            continue
        else:
            fresh_id = int(fresh_id)
        if len(account) > 4:
            fresh_basesids = account[4]
            if isinstance(fresh_basesids, list):
                if any(str(item).strip() and not str(item).strip().isdigit() for item in fresh_basesids):
                    smart_print(f"\n        ! Клиент: {fresh_name}: Определение идентификатора базы содержит непустимые символы")
                    error_count += 1
                    continue
                fresh_basesids = [int(item.strip()) for item in fresh_basesids if item and item.strip()]
            elif fresh_basesids is None or str(fresh_basesids).strip() == "":
                fresh_basesids = ""
            elif not str(fresh_basesids).strip().isdigit():
                smart_print(f"\n        ! Клиент: {fresh_name}: Определение идентификатора базы содержит непустимые символы")
                error_count += 1
                continue
            else:
                fresh_basesids = [int(item.strip())]
        else:
            fresh_basesids = ""
        main(fresh_login,fresh_password,fresh_id,fresh_name,fresh_basesids) # Передаём данные аккаунта далее

def main(fresh_login,fresh_password,fresh_id,fresh_name,fresh_basesids):
    global error_count, downloaded_count
    smart_print(f"\n    Клиент: {fresh_name}, ID абонента: {fresh_id}, Сервер: {fresh_server}")
    #smart_print(f"        Инициализация подключения")
    # Настройка авторизации
    password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    password_mgr.add_password(None, fresh_server, fresh_login, fresh_password)
    opener = urllib.request.build_opener(urllib.request.HTTPBasicAuthHandler(password_mgr))
    urllib.request.install_opener(opener)

    # Проверка версии API
    url_getversion = fresh_server + '/a/adm/hs/ext_api/version'
    try:
        with opener.open(url_getversion) as response:
            json_version_str = response.read().decode('utf-8')
            json_ver = json.loads(json_version_str)
            smart_print(f"        1C Major Ver: {json_ver['version']}; sm_version: {json_ver['sm_version']}")
    except Exception as e:
        smart_print(f"        ! Ошибка подключения: {e}")
        error_count += 1
        return # Возврат в account_init после ошибки

    if fresh_basesids:
        smart_print(f"        Скачивание архивов будет выполнено для баз: {', '.join(map(str, fresh_basesids))}")
   
    # Получение списка областей (tenants)
    #smart_print(f"        Получение списка областей для \"{fresh_name}\" ({fresh_id})")
    url_tenants_list = fresh_server + '/a/adm/hs/ext_api/execute'
    post_data_tenants = {
        "general": {"type": "ext", "method": "tenant/list", "debug": True},
        "auth": {"account": fresh_id}
    }
    try:
        request_tenants = urllib.request.Request(url_tenants_list, data=json.dumps(post_data_tenants).encode('utf-8'))
        with urllib.request.urlopen(request_tenants) as response:
            tenants_list_str = response.read().decode('utf-8')
        tenants = json.loads(tenants_list_str)['tenant']
        tenants_dict = {}
        for tenant in tenants:
            tenant_id = tenant['id']
            tenants_dict[tenant_id] = {
                'ts': '1970-01-01T00:00:01',
                'name': tenant['name'],
                'ver': tenant['app_version'],
                'app_name': tenant['app_name'],
                'app_id': tenant['id'],
                'app_version': tenant['app_version']
            }
    except Exception as e:
        smart_print(f"        ! Ошибка при получении списка областей: {e}")
        error_count += 1
        return # Возврат в account_init после ошибки
    
    # 3. Поиск последних бэкапов
    #smart_print(f"        Получение списка архивов")
    post_data_backup = {
        "general": {"type": "ext", "method": "backup/list", "debug": False},
        "auth": {"account": fresh_id}
    }
    try:
        request_backups = urllib.request.Request(url_tenants_list, data=json.dumps(post_data_backup).encode('utf-8'))
        with urllib.request.urlopen(request_backups) as response:
            blist_str = response.read().decode('utf-8') 
        backups = json.loads(blist_str)['backup']
        for backup in backups:
            tenant_id = backup['tenant']
            if tenant_id in tenants_dict and backup['timestamp'] > tenants_dict[tenant_id]['ts']:
                tenants_dict[tenant_id]['ts'] = backup['timestamp']
                tenants_dict[tenant_id]['uuid'] = backup['id']
    except Exception as e:
        smart_print(f"        ! Ошибка при получения списка архивов: {e}")
        error_count += 1
        return # Возврат в account_init после ошибки

    # Скачивание
    if not os.path.exists(backup_folder_path):
        os.makedirs(backup_folder_path)
        smart_print(f"        Создаём папку {backup_folder_path}")
    if not os.path.exists(list_folder_path):
        os.makedirs(list_folder_path)
    for tenant_id in tenants_dict:
        if 'uuid' not in tenants_dict[tenant_id]: continue
        db = tenants_dict[tenant_id]
        post_data_dl = {
            "id": db['uuid'],
            "general": {"version": 9, "type": "usr", "method": "backup/file_token/download", "debug": True},
            "auth": {"account": fresh_id, "type": "user"}
        }
        if not fresh_basesids or db.get('app_id') in fresh_basesids:
            try:
                req = urllib.request.Request(url_tenants_list, data=json.dumps(post_data_dl).encode('utf-8'))
                with urllib.request.urlopen(req) as response:
                    djson_obj = json.loads(response.read().decode('utf-8'))
                while 'task_id' in djson_obj:
                    clean_name = sanitize_filename(db['name'])
                    smart_print(f"        Ожидание формирования полного архива из диффа (60 секунд) для {clean_name}_{db['app_id']}")
                    time.sleep(60)
                    post_data_dl_dif = {
                        "id": db['uuid'],
                        "general": {"version": 9, "type": "usr", "method": "backup/file_token/download", "debug": True},
                        "auth": {"account": fresh_id, "type": "user"},
                        "task_id": djson_obj['task_id']
                    }
                    reqdif = urllib.request.Request(url_tenants_list, data=json.dumps(post_data_dl_dif).encode('utf-8'))
                    with urllib.request.urlopen(reqdif) as response:
                        djson_obj = json.loads(response.read().decode('utf-8'))
                if not djson_obj['general'].get('error'):
                    url = djson_obj['url']
                    clean_name = sanitize_filename(db['name'])
                    clean_ts = sanitize_filename(db['ts'])
                    archive_filename = f"{fresh_id}_{clean_name}_{db['app_id']}_{db['app_name']}_{db['app_version']}_{clean_ts}.zip"
                    archive_filepath = os.path.join(backup_folder_path,  archive_filename)
                    if check_free_space(url,archive_filepath,archive_filename) == 1:
                        error_count += 1
                        return # Возврат в account_init после ошибки
                    smart_print(f"        Скачиваем в {archive_filename} ...")
                    start_t = time.time()
                    try:
                        urllib.request.urlretrieve(url, archive_filepath)
                        duration = int(time.time() - start_t)
                        smart_print(f"        ОК, {duration} секунд(ы)")
                        # Записываем в файл-список успешно скачанный файл
                        with open(list_file_path, "a", encoding="utf-8") as list_f:
                            list_f.write(f"{archive_filename}\n")
                        downloaded_count += 1
                        
                    except Exception as e:
                        smart_print(f"        ! Ошибка при скачивании архива {archive_filename}: {e}")
                        error_count += 1
                        return # Возврат в account_init после ошибки
                else:
                    smart_print(f"        ! Ошибка API для {db['name']}: {djson_obj['general'].get('response')}")
                    error_count += 1
                    return # Возврат в account_init после ошибки
            except Exception as err:
                smart_print(f"        ! Непредвиденная ошибка для {db['name']}: {err}")
                error_count += 1
                #return # Возврат в account_init после ошибки
        else:
            clean_name = sanitize_filename(db['name'])
            smart_print(f"            ! База {clean_name} {db['app_id']} не найдена в перечне баз для скачивания архивов")
        time.sleep(cooldown_time)


def check_free_space(url,archive_filepath,archive_filename):
    global error_count
    #smart_print(f"        Проверка свободного места для скачивания архива {archive_filename}")
    try:
        # 1. Запрашиваем только заголовки через urllib, чтобы узнать размер файла
        with urllib.request.urlopen(url) as response:
            file_size = int(response.headers.get("Content-Length", 0))

        # 2. Определяем целевую папку и проверяем свободное место на нужном диске
        target_dir = os.path.dirname(os.path.abspath(archive_filepath))
        os.makedirs(target_dir, exist_ok=True)
        _, _, free_space = shutil.disk_usage(target_dir)

        # Запас 20 МБ на системные нужды Windows
        safety_buffer = 20 * 1024 * 1024 

        # 3. Проверяем условия и скачиваем через urlretrieve
        if file_size == 0:
            smart_print(f"        ! Не удаётся получить размер архива")
            smart_print(f"        Продолжаем работу, проверьте целостность архивов")
            return 0
        elif free_space > (file_size + safety_buffer):
            return 0
        else:
            smart_print(f"        ! Недостаточно свободного места для скачивания архива {archive_filename}")
            return 1

    except Exception as e:
        smart_print(f"        ! Ошибка при проверке свободного места: {e}")
        smart_print(f"        Продолжаем работу, проверьте целостность архивов")
        error_count += 1
        return 0 # Возврат в main после ошибки, считаем за невозможность получить размер файла и продолжаем

def test_7za():
    global error_count
    smart_print(f"\n=== Тестирование архивов ===\n")
    archive_extensions = ('.zip', '.7z', '.rar', '.tar', '.gz')
    corrupted_archives = []
    
    if not os.path.exists(exe_7za):
        smart_print(f"    ! Не удалось протестировать архивы: Путь '{exe_7za}' не найден.")
        error_count += 1
        return

    if not os.path.exists(backup_folder_path):
        smart_print(f"    ! Не удалось протестировать архивы: Путь '{backup_folder_path}' не найден.")
        error_count += 1
        return

    # Рекурсивный обход всех подпапок
    for root, dirs, files in os.walk(backup_folder_path):
        for file in files:
            if file.lower().endswith(archive_extensions):
                full_path = os.path.join(root, file)
                
                smart_print(f"    Тестирование архива: {file}...")
                
                # Запуск команды: 7za t "путь_к_файлу" -y
                # -y автоматически соглашается со всеми запросами утилиты
                result = subprocess.run(
                    [exe_7za, "t", full_path, "-y"],
                    stdout=subprocess.DEVNULL, # Глушим стандартный вывод 7za
                    stderr=subprocess.DEVNULL  # Глушим ошибки вывода 7za
                )
                
                # Если 7-Zip вернул код не 0, значит с архивом проблемы
                if result.returncode != 0:
                    smart_print(f"    Ошибка\n")
                    corrupted_archives.append(full_path)
                    error_count += 1
                else:
                    smart_print(f"    ОК\n")

    # Вывод результатов
    if corrupted_archives:
        smart_print(f"\nПовреждённых архивов: {len(corrupted_archives)}")
        for index, arch in enumerate(corrupted_archives, 1):
            smart_print(f"{index}. {arch}")
    else:
        smart_print("Ошибок не обнаружено")

def smart_print(message):
    if not os.path.exists(log_folder_path):
        os.makedirs(log_folder_path)
    """Выводит сообщение в консоль и записывает в лог-файл"""
    print(message)
    with open(log_file_path, "a", encoding="utf-8") as f:
        f.write(message + "\n")

def sanitize_filename(s_filename):
    """Очистка имени файла от запрещенных в Windows символов"""
    return re.sub(r'[\\/*?:"<>|]', "_", s_filename)

def dl_list_finalizing():
    # Добавляем итог в файл-список
    if downloaded_count > 0:
        with open(list_file_path, "a", encoding="utf-8") as list_f:
            list_f.write(f"\nВсего скачано файлов: {downloaded_count}\nЗавершено: {datetime.now()}")
        list_file_path_with_count = os.path.join(list_folder_path, f"list_{current_time_str}_dl-{downloaded_count}.txt")
        try:
            shutil.move(list_file_path, list_file_path_with_count)
        except Exception as e:
            error_count += 1
            smart_print(f"! Ошибка переименования списка файлов: {e}.")

def on_error_log():
    smart_print(f"\n!!! Работа завершена с количеством ошибок: {error_count}")
    shutil.copy(log_file_path, log_file_path_if_err_copy)
    shutil.move(log_file_path, log_file_path_if_err_rename)
    exit(-1)

def finalizing():
    smart_print(f"\nВсего скачано файлов: {downloaded_count}\nЗавершено: {datetime.now()}")
    if error_count > 0:
        on_error_log()
    else:
        smart_print(f"\n=== РАБОТА ЗАВЕРШЕНА ===")
        exit(0)

# Генерация имен файлов логов с текущей датой
error_count = 0
downloaded_count = 0  # Счетчик скачанных файлов
current_time = datetime.now()
current_time_str = current_time.strftime("%Y-%m-%d_%H-%M")
current_date_str = current_time.strftime("%Y-%m-%d")
list_folder_name = 'archives'
backup_folder_path = os.path.join(folder_path, list_folder_name)
backup_folder_path = os.path.join(backup_folder_path, current_date_str)
log_folder_name = '_logs'
log_file_name = f"log_{current_time_str}.txt"
log_file_name_if_err = f"_error-log_{current_time_str}.txt"
log_folder_path = os.path.join(folder_path, log_folder_name)
log_file_path = os.path.join(log_folder_path, log_file_name)
log_file_path_if_err_rename = os.path.join(log_folder_path, log_file_name_if_err)
log_file_path_if_err_copy = os.path.join(folder_path, log_file_name_if_err)
list_folder_name = '_lists'
list_file_name = f"list_{current_time_str}.txt"
list_folder_path = os.path.join(folder_path, list_folder_name)
list_file_path = os.path.join(list_folder_path, list_file_name)

# Начало работы
account_init(accounts_array)
dl_list_finalizing()
if exe_7za:
    test_7za()
finalizing()
