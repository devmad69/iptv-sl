#! /usr/bin/python3


import yt_dlp
import sys
import datetime
import time
import os
from threading import Thread
import queue
import json

# Cache file (relative to repo root). Script runs from scripts/ directory so use parent.
CACHE_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'assets', 'stream_cache.json'))
CACHE_TTL_SECONDS = 30 * 60  # 30 minutes

def load_cache():
    try:
        if os.path.exists(CACHE_PATH):
            with open(CACHE_PATH, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_cache(cache):
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        with open(CACHE_PATH, 'w') as f:
            json.dump(cache, f)
    except Exception:
        pass


def grab_with_timeout(url, timeout_sec=3):
    """
    Attempt to extract stream URL with explicit timeout using threading.
    If extraction takes longer than timeout_sec, return None.
    """
    result_queue = queue.Queue()
    
    def extract():
        try:
            urls_to_try = [url]
            if not url.endswith('/live'):
                urls_to_try.append(url + '/live')
            else:
                urls_to_try.append(url.replace('/live', ''))
            
            for attempt_url in urls_to_try:
                try:
                    ydl_opts = {
                        'quiet': True,
                        'no_warnings': True,
                        'geo_bypass': True,
                        'format': 'best',
                        'socket_timeout': 6,
                        'http_headers': {
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                        }
                    }
                    
                    # Add cookies if available from GitHub Actions secret (YT_COOKIES should contain the cookies.txt formatted content)
                    cookies_env = os.environ.get('YT_COOKIES')
                    temp_cookie_path = None
                    if cookies_env:
                        import tempfile
                        # Write the cookie text to a secure temporary file for yt-dlp
                        tf = tempfile.NamedTemporaryFile(mode='w', delete=False)
                        tf.write(cookies_env)
                        tf.flush()
                        temp_cookie_path = tf.name
                        tf.close()
                        ydl_opts['cookiefile'] = temp_cookie_path
                    
                    try:
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            info = ydl.extract_info(attempt_url, download=False)
                            if 'url' in info:
                                result_queue.put(('success', info['url']))
                                return
                    finally:
                        # Clean up temporary cookie file if we created one
                        if temp_cookie_path:
                            try:
                                os.remove(temp_cookie_path)
                            except Exception:
                                pass
                except Exception as e:
                    # Try next URL variant
                    continue
            
            # All URL variants failed
            result_queue.put(('fail', None))
        except Exception as e:
            result_queue.put(('fail', None))
    
    # Run extraction in background thread with timeout
    thread = Thread(target=extract, daemon=True)
    thread.start()
    thread.join(timeout=timeout_sec)
    
    # Check if thread is still alive (timed out)
    if thread.is_alive():
        print(f"Timeout: Channel {url} took too long (>{timeout_sec}s)", file=sys.stderr)
        return None
    
    # Get result from queue
    try:
        status, result = result_queue.get_nowait()
        return result if status == 'success' else None
    except queue.Empty:
        return None

def grab(url):
    """
    Extract stream URL with timeout protection and cache results.
    """
    cache = load_cache()
    stream_url = grab_with_timeout(url, timeout_sec=6)

    if stream_url:
        print(stream_url)
        # update cache
        try:
            cache[url] = {'url': stream_url, 'ts': int(time.time())}
            save_cache(cache)
        except Exception:
            pass
        return

    # If extraction failed, check cache for recent entry
    entry = cache.get(url)
    if entry and isinstance(entry, dict):
        try:
            if int(time.time()) - int(entry.get('ts', 0)) <= CACHE_TTL_SECONDS:
                cached_url = entry.get('url')
                if cached_url:
                    print(f"Using cached stream for {url}", file=sys.stderr)
                    print(cached_url)
                    return
        except Exception:
            pass

    # No valid cache, use placeholder
    print(f"Warning: Could not extract stream from {url}", file=sys.stderr)
    print('https://raw.githubusercontent.com/benmoose39/YouTube_to_m3u/main/assets/moose_na.m3u')


print('#EXTM3U x-tvg-url="https://github.com/botallen/epg/releases/download/latest/epg.xml"')
print(f'# Refreshed at {datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}')

with open('../youtube_channel_info.txt') as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith('~~'):
            continue
        if not line.startswith('https:'):
            line = line.split('|')
            ch_name = line[0].strip()
            grp_title = line[1].strip().title() if len(line) > 1 else ""
            tvg_logo = line[2].strip() if len(line) > 2 else ""
            tvg_id = line[3].strip() if len(line) > 3 else ""
            print(f'\n#EXTINF:-1 group-title="{grp_title}" tvg-logo="{tvg_logo}" tvg-id="{tvg_id}", {ch_name}')
        else:
            grab(line)

print("""
#EXTM3U
#EXTINF:-1 tvg-id="HiruTV" tvg-name="Hiru TV" tvg-logo="https://www.hirutv.lk/assets/images/logo.png" group-title="Sri Lanka",Hiru TV
https://tv.hiruhost.com:1936/8012/8012/playlist.m3u8

#EXTINF:-1 tvg-id="SiyathaTV" tvg-name="Siyatha TV" tvg-logo="https://voaplus.com/images/siyathatv-logo.jpg" group-title="Sri Lanka",Siyatha TV
https://rtmp01.voaplus.com/hls/6x6ik312qk4grfxocfcv_high/index.m3u8

#EXTINF:-1 tvg-id="Swarnawahini" tvg-name="Swarnawahini" tvg-logo="https://www.swarnavahini.lk/Uploads/logo.png" group-title="Sri Lanka",Swarnawahini
https://jk3lz8xklw79-hls-live.5centscdn.com/live/6226f7cbe59e99a90b5cef6f94f966fd.sdp/playlist.m3u8
""")