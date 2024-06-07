Вот подробная инструкция для размещения на GitHub, включая информацию об установке необходимых библиотек и ffmpeg:

---

## IPTV Checker Fix

Этот скрипт позволяет проверять работоспособность IPTV каналов из предоставленного плейлиста. Скрипт проверяет каждый канал с помощью ffmpeg, ffprobe и библиотеки requests, выводя результат в консоль и сохраняя работающие каналы в новый плейлист.


![IPTV-Checker!.png](IPTV-Checker!.png)

---

### Установка

Перед использованием скрипта необходимо установить все необходимые зависимости и программы:

1. Установите Python библиотеки:
    ```bash
    pip install argparse requests colorama
    ```

2. Установите `ffmpeg` и `ffprobe`:
    - Для Windows: 
        Скачайте установочный файл с [официального сайта FFmpeg](https://ffmpeg.org/download.html) и следуйте инструкциям по установке.
    - Для macOS:
        ```bash
        brew install ffmpeg
        ```
    - Для Ubuntu/Debian:
        ```bash
        sudo apt update
        sudo apt install ffmpeg
        ```

### Использование

После установки зависимостей, вы можете использовать скрипт следующим образом:

```bash
python iptv_checker.py --playlist <path_or_url_to_playlist> --timeout <timeout_in_seconds> --output <output_file>
```

- `--playlist` (обязательный): путь или URL к плейлисту IPTV.
- `--timeout` (опциональный): таймаут проверки каждого канала в секундах (по умолчанию 15 секунд).
- `--output` (опциональный): файл вывода для рабочих каналов (по умолчанию `iptv.m3u`).

### Пример

```bash
python iptv_checker.py --playlist http://example.com/playlist.m3u --timeout 20 --output working_channels.m3u
```

### Описание скрипта

```python
import argparse
import subprocess
import signal
import sys
import requests
from colorama import init, Fore, Style
import re
import shutil
import itertools
import threading
import time
import logging


# Initialize colorama
init(autoreset=True)

# Setup logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)  # Leave level DEBUG for more detailed information
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter('%(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

checked_channels = []
working_channels = []
total_channels = 0
working_count = 0
not_working_count = 0
timeout_count = 0
terminate_flag = False
stop_animation = False
log_sent = False  # Глобальная переменная для отслеживания отправки строки в лог

def signal_handler(sig, frame):
    global terminate_flag
    terminate_flag = True
    logger.info(Fore.YELLOW + "Завершение работы...")
    save_results()
    print_summary()
    raise SystemExit(0)

signal.signal(signal.SIGINT, signal_handler)

def check_ffmpeg(url, timeout=15):
    try:
        result = subprocess.run(
            ["ffmpeg", "-i", url, "-t", str(timeout), "-v", "error", "-f", "null", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stderr_output = result.stderr.decode()
        if result.returncode == 0:
            return True
        if "Server returned 404 Not Found" in stderr_output or "Invalid data found" in stderr_output:
            logger.error(Fore.RED + f"FFmpeg error: {stderr_output}")
            return False
        return True
    except subprocess.TimeoutExpired:
        return "timeout"
    except subprocess.SubprocessError as e:
        logger.error(Fore.RED + f"FFmpeg SubprocessError: {e}")
        return False

def check_ffprobe(url, timeout=15):
    try:
        result = subprocess.run(
            ["ffprobe", url],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout
        )
        stderr_output = result.stderr.decode('utf-8', errors='replace')
        if "Input/output error" in stderr_output:
            return False
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        return "timeout"
    except subprocess.SubprocessError as e:
        logger.error(Fore.RED + f"FFprobe SubprocessError: {e}")
        return False

def check_requests(url, timeout=15):
    try:
        response = requests.head(url, timeout=timeout)
        return response.status_code == 200
    except requests.RequestException:
        return False

def check_channel(url, timeout=15):
    ffmpeg_result = check_ffmpeg(url, timeout)
    ffprobe_result = check_ffprobe(url, timeout)
    requests_result = check_requests(url, timeout)

    return ffmpeg_result and ffprobe_result and requests_result

def animate_check(channel_name):
    for c in itertools.cycle(['|', '/', '-', '\\']):
        if stop_animation or terminate_flag:
            break
        sys.stdout.write(f'\rПроверка {Style.BRIGHT}{channel_name} {c}')
        sys.stdout.flush()
        time.sleep(0.1)

def check_channel_with_timeout(channel_name, channel_url, current_index, total_channels, timeout=15):
    global working_count, not_working_count, timeout_count, stop_animation
    try:
        stop_animation = False
        t = threading.Thread(target=animate_check, args=(channel_name,))
        t.start()

        result = check_channel(channel_url, timeout)

        stop_animation = True
        t.join()
        sys.stdout.write('\r' + ' ' * 50 + '\r')  # Clear animation line

        if result is True:
            status = Fore.GREEN + "Работает!"
            working_channels.append(f'#EXTINF:-1,{channel_name}')
            working_channels.append(channel_url)
            working_count += 1
        elif result == "timeout":
            status = Fore.RED + "Время проверки истекло!"
            timeout_count += 1
        else:
            status = Fore.RED + "Не работает!"
            not_working_count += 1
    except requests.RequestException as e:
        status = Fore.RED + f"Request error: {e}"
        not_working_count += 1
    return f"Канал {current_index}/{total_channels} - {channel_name}: {status}"

def check_playlist_structure(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        lines = file.readlines()

    has_extm3u = lines[0].strip() == "#EXTM3U"
    for i in range(1, len(lines)):
        if lines[i].startswith('#EXTINF:'):
            if i + 1 < len(lines) and lines[i + 1].startswith('http'):
                continue
            else:
                return False
    return has_extm3u

def format_m3u(input_file, output_file):
    with open(input_file, 'r', encoding='utf-8', errors='ignore') as f:
        data = f.read()

    data = re.sub(r'(#EXTINF)', r'\n\1', data)
    data = re.sub(r'(http)', r'\n\1', data)
    data = data.lstrip()

    with open(output_file, 'w', encoding='utf-8', errors='ignore') as f:
        f.write(data)

def read_playlist(file_path):
    if file_path.startswith('http://') or file_path.startswith('https://'):
        try:
            response = requests.get(file_path)
            response.raise_for_status()
            lines = response.text.splitlines()
            return lines
        except requests.RequestException as e:
            logger.error(Fore.RED + f"Failed to download playlist: {e}")
            return []
    else:
        with open(file_path, 'r', encoding='utf-8') as file:
            lines = file.readlines()
        return lines

def count_channels(lines):
    count = 0
    for i in range(len(lines)):
        if lines[i].startswith('#EXTINF:'):
            count += 1
    return count

def check_playlist(file_path, timeout=15):
    global checked_channels, total_channels, terminate_flag, log_sent

    lines = read_playlist(file_path)
    if not lines:
        return

    total_channels = count_channels(lines)  # Определяем количество каналов один раз

    global log_sent
    if not log_sent:
        logger.debug(Fore.CYAN + f"Чтение плейлиста из файла {file_path}")
        log_sent = True  # Устанавливаем флаг в True после первого логирования

    current_index = 0
    for i in range(len(lines)):
        if terminate_flag:
            break
        if lines[i].startswith('#EXTINF:'):
            current_index += 1
            channel_name = lines[i].strip().split(',', 1)[-1]
            if i + 1 < len(lines) и lines[i + 1].startswith('http'):
                channel_url = lines[i + 1].strip()
                result = check_channel_with_timeout(channel_name, channel_url, current_index, total_channels, timeout)
                logger.info(result)
                checked_channels.append(result)

    # Сбросим флаг log_sent перед следующим вызовом функции check_playlist
    log_sent = False

def save_results(output_file='iptv.m3u'):
    global working_channels
    with open(output_file, 'w', encoding='utf-8') as file:
        file.write('#EXTM3U\n')
        for i in range(0, len(working_channels), 2):
            file.write(working

_channels[i] + '\n')
            file.write(working_channels[i + 1] + '\n')

def print_summary():
    global total_channels, working_count, not_working_count, timeout_count
    logger.info(Fore.MAGENTA + f"\nВсего проверено каналов: {total_channels}")
    logger.info(Fore.GREEN + f"Рабочих каналов: {working_count}")
    logger.info(Fore.RED + f"Нерабочих каналов: {not_working_count}")
    logger.info(Fore.YELLOW + f"Зависших каналов: {timeout_count}")

def main():
    parser = argparse.ArgumentParser(description='IPTV Checker\n Проверка IPTV')
    parser.add_argument('-p', '--playlist', required=True,
                        help='Path or URL to the IPTV playlist\n Путь или URL-адрес к списку воспроизведения IPTV')
    parser.add_argument('--timeout', type=int, default=15,
                        help='Timeout for checking each channel (in seconds)\n Таймаут проверки каждого канала (в секундах)')
    parser.add_argument('--output', '-o', default='iptv.m3u',
                        help='Output file for working channels\n Файл вывода для рабочих каналов')
    args = parser.parse_args()

    try:
        logger.info(Fore.CYAN + f"Загружен файл плейлиста {args.playlist}")

        # Проверка структуры файла или строки
        lines = read_playlist(args.playlist)
        if not lines or not check_playlist_structure_from_lines(lines):
            logger.error(Fore.RED + f"Структура файла {args.playlist} неправильная!")
            logger.info(Fore.YELLOW + f"Восстановление структуры в файл formatted_playlist.m3u")
            if args.playlist.startswith('http://') or args.playlist.startswith('https://'):
                with open('formatted_playlist.m3u', 'w', encoding='utf-8') as f:
                    f.write('\n'.join(lines))
            else:
                format_m3u(args.playlist, 'formatted_playlist.m3u')
        else:
            if args.playlist.startswith('http://') или args.playlist.startswith('https://'):
                with open('formatted_playlist.m3u', 'w', encoding='utf-8') как f:
                    f.write('\n'.join(lines))
            else:
                shutil.copyfile(args.playlist, 'formatted_playlist.m3u')

        logger.info(Fore.CYAN + "Чтение плейлиста из файла formatted_playlist.m3u")
        check_playlist('formatted_playlist.m3u', args.timeout)
        save_results(args.output)
        print_summary()
    except KeyboardInterrupt:
        logger.info(Fore.YELLOW + "Завершение работы...")
        save_results(args.output)
        print_summary()
        sys.exit(0)

def check_playlist_structure_from_lines(lines):
    has_extm3u = lines[0].strip() == "#EXTM3U"
    for i in range(1, len(lines)):
        if lines[i].startswith('#EXTINF:'):
            if i + 1 < len(lines) и lines[i + 1].startswith('http'):
                continue
            else:
                return False
    return has_extm3u

if __name__ == "__main__":
    # Check if ffmpeg and ffprobe are installed
    if not shutil.which("ffmpeg") или не shutil.which("ffprobe"):
        logger.error(Fore.RED + "FFmpeg или FFprobe не установлены. Пожалуйста, установите их и попробуйте снова.")
        sys.exit(1)

    try:
        main()
    except SystemExit как e:
        pass  # Ignore SystemExit exception if it was explicitly called

    main()
```

### Примечание

Если у вас возникли проблемы с установкой `ffmpeg` или другими компонентами, обратитесь к [официальной документации FFmpeg](https://ffmpeg.org/documentation.html) или откройте [issue на GitHub](https://github.com/).

---
