import yt_dlp
import sys
import subprocess

def stream_video(url, format_id):
    ydl_opts_info = {
        'quiet': True,
        'no_playlist': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
        info = ydl.extract_info(url, download=False)
        needs_audio = False
        chosen = next((f for f in info.get('formats', []) if f['format_id'] == format_id), None)
        if chosen and chosen.get('vcodec') != 'none' and chosen.get('acodec') == 'none':
            needs_audio = True

        if needs_audio:
            v_url = chosen['url']
            audio = next((f for f in reversed(info['formats']) if f.get('acodec') != 'none' and (f.get('vcodec') == 'none' or not f.get('vcodec'))), None)
            if not audio:
                audio = next((f for f in info['formats'] if f.get('acodec') != 'none'), None)

            a_url = audio['url'] if audio else v_url
            ua = info.get('http_headers', {}).get('User-Agent', 'Mozilla/5.0')
            
            ffmpeg_cmd = [
                'ffmpeg',
                '-user_agent', ua,
                '-i', v_url,
                '-user_agent', ua,
                '-i', a_url,
                '-c', 'copy',
                '-f', 'matroska',
                'pipe:1'
            ]
            print(f"FFMPEG COMMAND: {' '.join(ffmpeg_cmd)}")
            
            process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return process
            
def test():
    url = "https://www.youtube.com/watch?v=aqz-KE-bpKQ"
    ydl_opts_info = {'quiet': True, 'no_playlist': True}
    with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
        info = ydl.extract_info(url, download=False)
        test_format = next(f for f in info['formats'] if f.get('height') == 1080)
        
    print(f"Testing streaming for format {test_format['format_id']}")
    process = stream_video(url, test_format['format_id'])
    
    print("FFMPEG STDERR:")
    import time
    time.sleep(3)
    process.terminate()
    out, err = process.communicate()
    if err:
        print(err.decode('utf-8', errors='ignore'))
    
if __name__ == "__main__":
    test()
