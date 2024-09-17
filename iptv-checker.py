import os, requests, argparse, logging, concurrent.futures, subprocess, time, signal, sys, threading, urllib3, shutil
from tqdm import tqdm
from colorama import Fore, Style, init


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Инициализация colorama для Windows и Linux
init(autoreset=True)

# Логирование для дебага
logging.basicConfig(filename='iptv_check.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


# Статистика каналов с использованием класса
class Stats:
    def __init__(self):
        self.working = 0
        self.failed = 0
        self.timeout = 0
        self.skipped = 0

    def log_summary(self):
        total = self.working + self.failed + self.timeout + self.skipped
        logging.info(f"=== Summary ===")
        logging.info(f"Total channels: {total}")
        if total > 0:
            logging.info(f"Working: {self.working} ({self.working / total * 100:.2f}%)")
            logging.info(f"Failed: {self.failed} ({self.failed / total * 100:.2f}%)")
            logging.info(f"Timeouts: {self.timeout} ({self.timeout / total * 100:.2f}%)")
            logging.info(f"Skipped: {self.skipped} ({self.skipped / total * 100:.2f}%)")
        else:
            logging.info("No channels processed.")

    def print_summary(self):
        total = self.working + self.failed + self.timeout + self.skipped
        print(f"\n{Fore.YELLOW}=== Statistics ==={Style.RESET_ALL}")
        print(
            f"{Fore.GREEN}Working channels added: {self.working} ({self.working / total * 100:.2f}%)" if total > 0 else "No channels processed.")
        print(
            f"{Fore.RED}Failed channels removed: {self.failed} ({self.failed / total * 100:.2f}%)" if total > 0 else "")
        print(f"{Fore.BLUE}Timeouts: {self.timeout} ({self.timeout / total * 100:.2f}%)" if total > 0 else "")
        print(
            f"{Fore.YELLOW}Skipped channels: {self.skipped} ({self.skipped / total * 100:.2f}%){Style.RESET_ALL}" if total > 0 else "")


stats = Stats()
RETRY_COUNT = 1

# Путь к файлу пропущенных каналов
SKIPPED_FILE_PATH = 'other/skipped.txt'
os.makedirs(os.path.dirname(SKIPPED_FILE_PATH), exist_ok=True)

lock = threading.Lock()


def signal_handler(sig, frame):
    print("\nGracefully shutting down...")
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)


def check_dependencies():
    # Проверка наличия ffmpeg с помощью shutil.which
    ffmpeg_path = shutil.which('ffmpeg')

    if ffmpeg_path is None:
        print(f"{Fore.RED}ffmpeg не установлен или не найден в PATH!{Style.RESET_ALL}")
        sys.exit(1)
    else:
        try:
            subprocess.run([ffmpeg_path, '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            print(f"{Fore.GREEN}ffmpeg найден по пути: {ffmpeg_path}{Style.RESET_ALL}")
        except subprocess.CalledProcessError:
            print(f"{Fore.RED}Ошибка при попытке выполнить ffmpeg!{Style.RESET_ALL}")
            sys.exit(1)

    # Проверка других зависимостей при необходимости
    try:
        import requests
    except ImportError:
        print(f"{Fore.RED}Пакет requests не установлен!{Style.RESET_ALL}")
        sys.exit(1)


# Кэш для хранения результатов проверки
cache = {}


def check_stream(url, channel_name, headers=None, ffmpeg_timeout=25):
    if url in cache:
        return cache[url]

    for attempt in range(RETRY_COUNT + 1):
        try:
            logging.debug(
                f"Checking stream: {channel_name} ({url}) with headers: {headers}) - Attempt {attempt + 1}")

            if url.startswith('http://') or url.startswith('https://'):
                response = requests.head(url, headers=headers, timeout=15, verify=False)
                if response.status_code != 200:
                    stats.failed += 1
                    cache[url] = (False, f"Invalid status code: {response.status_code}")
                    return False, f"Invalid status code: {response.status_code}"

                logging.debug(f"HEAD request successful for {url}, proceeding to ffmpeg check")

            ffmpeg_command = ['ffmpeg', '-i', url, '-t', '5', '-f', 'null', '-']
            try:
                result = subprocess.run(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        timeout=ffmpeg_timeout)
                if result.returncode == 0:
                    stats.working += 1
                    cache[url] = (True, None)
                    return True, None
                else:
                    stats.failed += 1
                    cache[url] = (False, "Stream does not work")
                    return False, "Stream does not work"
            except subprocess.TimeoutExpired:
                logging.error(f"ffmpeg timeout for {channel_name} (attempt {attempt + 1})")
                stats.timeout += 1
                if attempt == RETRY_COUNT:
                    cache[url] = (False, "ffmpeg timeout")
                    return False, "ffmpeg timeout"

        except requests.exceptions.Timeout:
            logging.error(f"Timeout error for {channel_name} (attempt {attempt + 1})")
            stats.timeout += 1
            if attempt == RETRY_COUNT:
                cache[url] = (False, "Request timeout")
                return False, "Request timeout"
        except requests.exceptions.RequestException as e:
            logging.error(f"Request error for {channel_name} (attempt {attempt + 1}): {e}")
            simplified_error = simplify_error(str(e))
            if attempt == RETRY_COUNT:
                stats.failed += 1
                cache[url] = (False, simplified_error)
                return False, simplified_error
        except Exception as e:
            logging.error(f"General error for {channel_name}: {e}")
            if attempt == RETRY_COUNT:
                stats.failed += 1
                cache[url] = (False, "General error")
                return False, "General error"


def simplify_error(error_message):
    error_map = {
        "No connection adapters": "No connection!",
        "Timeout": "Request timeout",
        "403 Forbidden": "Access forbidden (403)"
    }
    for error, message in error_map.items():
        if error in error_message:
            return message
    return "Request error"


def get_unique_filename(directory, filename):
    base, ext = os.path.splitext(filename)
    new_filename = filename
    for i in range(1, 101):
        if not os.path.exists(os.path.join(directory, new_filename)):
            break
        new_filename = f"{base}_{i}{ext}"
    return new_filename


def add_extm3u_line(content):
    return "#EXTM3U url-tvg=\"http://iptvx.one/epg/epg.xml.gz\"\n" + content


def process_playlist(playlist, save_file, num_threads, ffmpeg_timeout):
    check_dependencies()
    if not save_file:
        save_file = os.path.join('output', get_unique_filename('output', 'default.m3u'))

    if playlist.startswith('http'):
        try:
            content = requests.get(playlist).text
        except requests.RequestException as e:
            logging.error(f"Failed to download playlist: {e}")
            sys.exit(1)
    else:
        try:
            with open(playlist, 'r') as f:
                content = f.read()
        except FileNotFoundError:
            logging.error(f"File {playlist} not found")
            sys.exit(1)
        except IOError as e:
            logging.error(f"Error reading file {playlist}: {e}")
            sys.exit(1)

    content = add_extm3u_line(content)
    lines = content.splitlines()
    updated_lines = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        future_to_url = {}
        num_channels = len([line for line in lines if line.startswith("#EXTINF")])
        pbar = tqdm(total=num_channels, desc="Checking channels", ncols=100, colour="green")

        for i, line in enumerate(lines):
            if line.startswith("#EXTINF"):
                if i + 1 < len(lines) and lines[i + 1].startswith('http'):
                    url = lines[i + 1]
                    channel_name = line.split(",")[-1]
                    headers = {}
                    future = executor.submit(check_stream, url, channel_name, headers, ffmpeg_timeout)
                    future_to_url[future] = (line, url)

        try:
            for future in concurrent.futures.as_completed(future_to_url):
                extinf_line, url = future_to_url[future]
                try:
                    success, error = future.result()
                    if success:
                        updated_lines.append(extinf_line)
                        updated_lines.append(url)
                        print(f"{Fore.GREEN}[SUCCESS] {extinf_line.split(',')[-1]}{Style.RESET_ALL}")
                    else:
                        print(f"{Fore.RED}[FAIL] {extinf_line.split(',')[-1]} - {error}{Style.RESET_ALL}")
                        logging.error(f"Failed to play {url}: {error}")
                except concurrent.futures.TimeoutError:
                    with lock:
                        print(f"{Fore.YELLOW}[SKIPPED] {extinf_line.split(',')[-1]} - Took too long{Style.RESET_ALL}")
                        stats.skipped += 1
                        with open(SKIPPED_FILE_PATH, 'a') as f:
                            f.write(f"{extinf_line}\n{url}\n")
                pbar.update(1)

        except concurrent.futures.TimeoutError:
            print(f"{Fore.RED}Processing took too long!{Style.RESET_ALL}")

        finally:
            pbar.close()

    with open(save_file, 'w') as f:
        for line in updated_lines:
            f.write(line + "\n")

    print(f"\n{Fore.CYAN}Playlist saved to {save_file}{Style.RESET_ALL}")
    stats.log_summary()
    stats.print_summary()


def process_files_in_directory(input_dir, output_dir, num_threads, ffmpeg_timeout):
    input_files = [f for f in os.listdir(input_dir) if f.endswith('.m3u') or f.endswith('.m3u8')]

    # Лог количества файлов
    logging.info(f"Found {len(input_files)} playlists in directory.")

    for playlist in input_files:
        input_path = os.path.join(input_dir, playlist)
        save_path = os.path.join(output_dir, get_unique_filename(output_dir, playlist))

        logging.info(f"Processing file: {input_path}")

        # Сброс статистики для каждого плейлиста, если требуется отдельная статистика
        # stats = Stats()  # Раскомментируйте, если хотите сбрасывать статистику для каждого файла

        process_playlist(input_path, save_path, num_threads, ffmpeg_timeout)

        logging.info(f"Finished processing file: {input_path}")


def main():
    parser = argparse.ArgumentParser(description="IPTV playlist checker")
    parser.add_argument('-p', '--playlist', help="URL or path to the playlist file")
    parser.add_argument('-s', '--save', help="Path to save the checked playlist")
    parser.add_argument('-t', '--threads', type=int, default=1, help="Number of threads for checking streams")
    parser.add_argument('-ft', '--ffmpeg-timeout', type=int, default=15, help="Timeout for ffmpeg (in seconds)")
    parser.add_argument('-file', action="store_true", help="Process all playlist files from the input folder")
    args = parser.parse_args()

    if args.file:
        input_dir = 'input'
        output_dir = 'output'
        os.makedirs(output_dir, exist_ok=True)
        process_files_in_directory(input_dir, output_dir, args.threads, args.ffmpeg_timeout)
    else:
        if not args.playlist:
            parser.error("Playlist URL or file path is required unless using -file option.")
        process_playlist(args.playlist, args.save, args.threads, args.ffmpeg_timeout)


if __name__ == '__main__':
    main()
