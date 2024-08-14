import argparse
import subprocess
import signal
import sys
import requests
from colorama import init, Fore
import re
import shutil
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

# Initialize colorama
init(autoreset=True)

# Setup logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter('%(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Global variables
checked_channels = []
working_channels = []
total_channels = 0
working_count = 0
not_working_count = 0
timeout_count = 0
terminate_flag = False
executor = None  # Для управления потоками

def signal_handler(sig, frame):
    global terminate_flag
    terminate_flag = True
    logger.info(Fore.YELLOW + "\nTerminating...")
    if executor:
        logger.info(Fore.YELLOW + "Waiting for threads to finish...")
        executor.shutdown(wait=True)  # Ожидание завершения всех потоков
    save_results()
    print_summary()
    sys.exit(0)  # Мягкое завершение программы

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

def check_channel_with_timeout(channel_name, channel_url, current_index, total_channels, timeout=15):
    global working_count, not_working_count, timeout_count
    # Отображение информации о текущей проверке канала
    sys.stdout.write(f"\r{Fore.CYAN}Проверка {current_index}/{total_channels} - {channel_name}... ")
    sys.stdout.flush()

    try:
        result = check_channel(channel_url, timeout)

        if result is True:
            status = Fore.GREEN + "Работает!"
            working_channels.append(f'#EXTINF:-1,{channel_name}')
            working_channels.append(channel_url)
            working_count += 1
        elif result == "timeout":
            status = Fore.RED + "Таймаут!"
            timeout_count += 1
        else:
            status = Fore.RED + "Не работает!"
            not_working_count += 1
    except requests.RequestException as e:
        status = Fore.RED + f"Ошибка запроса: {e}"
        not_working_count += 1

    # Обновление статуса после проверки канала
    sys.stdout.write(f"\r{Fore.CYAN}Канал {current_index}/{total_channels} - {channel_name}: {status}\n")
    sys.stdout.flush()
    return f"Канал {current_index}/{total_channels} - {channel_name}: {status}"

def read_playlist(file_path):
    if file_path.startswith('http://') or file_path.startswith('https://'):
        try:
            response = requests.get(file_path)
            response.raise_for_status()
            return response.text.splitlines()
        except requests.RequestException as e:
            logger.error(Fore.RED + f"Не удалось скачать плейлист: {e}")
            return []
    else:
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.readlines()

def count_channels(lines):
    return sum(1 for line in lines if line.startswith('#EXTINF:'))

def check_playlist(file_path, timeout=15):
    lines = read_playlist(file_path)
    if not lines:
        return

    global total_channels, executor
    total_channels = count_channels(lines)

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = []
        current_index = 0
        for i, line in enumerate(lines):
            if terminate_flag:
                break  # Прекращаем проверку, если получен сигнал прерывания
            if line.startswith('#EXTINF:'):
                current_index += 1
                channel_name = line.split(',', 1)[-1].strip()
                if i + 1 < len(lines) and lines[i + 1].startswith('http'):
                    channel_url = lines[i + 1].strip()
                    futures.append(executor.submit(check_channel_with_timeout, channel_name, channel_url, current_index, total_channels, timeout))

        for future in as_completed(futures):
            if terminate_flag:
                break  # Останавливаем выполнение оставшихся задач
            future.result()  # Ждём завершения проверки

def remove_duplicates(channels):
    unique_entries = {}  # Используем словарь для хранения уникальных пар "имя канала: URL"
    for i in range(0, len(channels), 2):
        channel_info = channels[i]  # строка с именем канала (например, #EXTINF)
        channel_url = channels[i + 1]  # строка с URL канала

        # Извлекаем имя канала из строки #EXTINF
        channel_name = channel_info.split(',', 1)[-1].strip()

        # Проверяем уникальность по имени канала
        if channel_name not in unique_entries:
            unique_entries[channel_name] = (channel_info, channel_url)
        else:
            # Обновляем запись, если нужно (например, заменяем на последний найденный URL)
            unique_entries[channel_name] = (channel_info, channel_url)

    # Преобразуем словарь обратно в список
    unique_channels = []
    for name, (info, url) in unique_entries.items():
        unique_channels.append(info)
        unique_channels.append(url)

    return unique_channels

def save_results(output_file='iptv.m3u'):
    global working_channels
    # Удаляем дубликаты перед сохранением
    working_channels = remove_duplicates(working_channels)
    with open(output_file, 'w', encoding='utf-8') as file:
        file.write('#EXTM3U\n')
        for i in range(0, len(working_channels), 2):
            file.write(working_channels[i] + '\n')
            file.write(working_channels[i + 1] + '\n')

def print_summary():
    logger.info(Fore.MAGENTA + f"\nВсего проверено каналов: {total_channels}")
    logger.info(Fore.GREEN + f"Рабочих каналов: {working_count}")
    logger.info(Fore.RED + f"Нерабочих каналов: {not_working_count}")
    logger.info(Fore.YELLOW + f"Каналов с таймаутом: {timeout_count}")

def main():
    parser = argparse.ArgumentParser(description='IPTV Checker\n')
    parser.add_argument('-p', '--playlist', required=True, help='Путь или URL к плейлисту IPTV')
    parser.add_argument('--timeout', type=int, default=15, help='Таймаут для проверки каждого канала (в секундах)')
    parser.add_argument('--output', '-o', default='iptv.m3u', help='Файл для рабочих каналов')
    args = parser.parse_args()

    logger.info(Fore.CYAN + f"Загрузка плейлиста из {args.playlist}")
    check_playlist(args.playlist, args.timeout)
    save_results(args.output)
    print_summary()

if __name__ == "__main__":
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        logger.error(Fore.RED + "FFmpeg или FFprobe не установлены.")
        sys.exit(1)

    try:
        main()
    except SystemExit:
        pass
