from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, session
import subprocess, os, uuid, threading, json
from datetime import datetime
import functools

app = Flask(__name__)
app.secret_key = 'videopro_2024_secret'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['PROCESSED_FOLDER'] = 'processed'
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024 * 1024  # 1GB

os.makedirs('uploads', exist_ok=True)
os.makedirs('processed', exist_ok=True)
os.makedirs('data', exist_ok=True)

progress = {}
ad_credits = {}

def load_stats():
    try:
        with open('data/stats.json', 'r') as f: return json.load(f)
    except:
        return {'total_visits':0, 'total_videos':0, 'functions_used':{}, 'visits_by_hour':{}, 'users_ip':[], 'history':[], 'ad_views':0}

def save_stats(s): 
    with open('data/stats.json', 'w') as f: json.dump(s, f)

ADMIN_USER = "admin"
ADMIN_PASS = "videopro2024"

def login_required(f):
    @functools.wraps(f)
    def d(*a, **k):
        if not session.get('logged_in'): return redirect(url_for('admin_login'))
        return f(*a, **k)
    return d

@app.route('/')
def index():
    s = load_stats()
    s['total_visits'] += 1
    s['visits_by_hour'][datetime.now().strftime('%H')] = s['visits_by_hour'].get(datetime.now().strftime('%H'), 0) + 1
    ip = request.remote_addr
    if ip not in s['users_ip']: s['users_ip'].append(ip)
    save_stats(s)
    return render_template('index.html')

@app.route('/watch_ad', methods=['POST'])
def watch_ad():
    uid = request.remote_addr
    ad_credits[uid] = ad_credits.get(uid, 0) + 1
    s = load_stats()
    s['ad_views'] += 1
    save_stats(s)
    return jsonify({'credits': ad_credits[uid]})

@app.route('/get_credits')
def get_credits():
    return jsonify({'credits': ad_credits.get(request.remote_addr, 0)})

@app.route('/upload', methods=['POST'])
def upload():
    if 'video' not in request.files: return jsonify({'error': 'No video'}), 400
    file = request.files['video']
    if file.filename == '': return jsonify({'error': 'No seleccionado'}), 400
    
    job_id = str(uuid.uuid4())[:8]
    ext_in = file.filename.rsplit('.', 1)[-1] if '.' in file.filename else 'mp4'
    input_path = f"uploads/{job_id}_input.{ext_in}"
    file.save(input_path)
    
    functions_json = request.form.get('functions', '[]')
    try:
        selected_funcs = json.loads(functions_json)
    except:
        selected_funcs = [{'func': request.form.get('function', 'vypeo'), 'tier': 'free'}]
    
    options = {
        'functions': selected_funcs,
        'fps': request.form.get('fps', '60'),
    }
    
    s = load_stats()
    s['total_videos'] += 1
    for f in selected_funcs:
        func_name = f.get('func', 'desconocido')
        s['functions_used'][func_name] = s['functions_used'].get(func_name, 0) + 1
    s['history'].append({
        'job_id': job_id,
        'time': datetime.now().strftime('%H:%M:%S'),
        'functions': [f.get('func','?') for f in selected_funcs],
        'filename': file.filename[:25]
    })
    if len(s['history']) > 50: s['history'] = s['history'][-50:]
    save_stats(s)
    
    output_path = f"processed/processed_{job_id}.mp4"
    threading.Thread(target=process_video, args=(input_path, output_path, options, job_id)).start()
    return jsonify({'job_id': job_id})

def run_ffmpeg(cmd, job_id, progress_val):
    global progress
    progress[job_id] = progress_val
    subprocess.run(cmd, check=True)

def process_video(input_path, output_path, options, job_id):
    global progress
    progress[job_id] = 0
    funcs = options.get('functions', [])
    fps = options.get('fps', '60')
    
    current_input = input_path
    temp_counter = 0
    
    def get_temp():
        nonlocal temp_counter
        temp_counter += 1
        return f"uploads/temp_{job_id}_{temp_counter}.mp4"
    
    # Procesar cada funcion en orden
    for func_data in funcs:
        func = func_data.get('func', 'vypeo')
        temp_output = get_temp()
        progress[job_id] = min(90, int((len(funcs) - funcs.index(func_data)) / len(funcs) * 90))
        
        try:
            # BLOQUE 1: BASICOS ESENCIALES (GRATIS)
            if func == 'vypeo':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-c', 'copy', temp_output], job_id, progress[job_id])
            elif func == 'trim_video':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-ss', '00:00:01', '-t', '00:00:30', '-c', 'copy', temp_output], job_id, progress[job_id])
            elif func == 'compress_low':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-c:v', 'libx264', '-crf', '28', '-preset', 'ultrafast', '-c:a', 'aac', '-b:a', '64k', temp_output], job_id, progress[job_id])
            elif func == 'mute_video':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-c:v', 'copy', '-an', temp_output], job_id, progress[job_id])
            elif func == 'extract_audio':
                temp_output = temp_output.replace('.mp4', '.mp3')
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vn', '-c:a', 'libmp3lame', '-b:a', '320k', temp_output], job_id, progress[job_id])
            elif func == 'to_gif':
                temp_output = temp_output.replace('.mp4', '.gif')
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', 'fps=10,scale=480:-1', '-c:v', 'gif', temp_output], job_id, progress[job_id])
            elif func == 'reverse_video':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', 'reverse', '-af', 'areverse', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '18', temp_output], job_id, progress[job_id])
            elif func == 'rotate_90_r':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', 'transpose=1', '-c:a', 'copy', temp_output], job_id, progress[job_id])
            elif func == 'flip_h':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', 'hflip', '-c:a', 'copy', temp_output], job_id, progress[job_id])
            elif func == 'change_speed_2x':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', 'setpts=0.5*PTS', '-af', 'atempo=2.0', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '18', temp_output], job_id, progress[job_id])
            
            # BLOQUE 2: OPTIMIZADORES DE REDES (GRATIS)
            elif func == 'ratio_tiktok':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', 'crop=ih*9/16:ih,scale=1080:1920', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '18', '-c:a', 'aac', '-b:a', '128k', temp_output], job_id, progress[job_id])
            elif func == 'ratio_reels':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', 'crop=ih*9/16:ih,scale=1080:1920', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '18', '-c:a', 'aac', '-b:a', '128k', temp_output], job_id, progress[job_id])
            elif func == 'ratio_yt':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', 'scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '18', '-c:a', 'aac', '-b:a', '192k', temp_output], job_id, progress[job_id])
            elif func == 'ratio_shorts':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', 'crop=ih*9/16:ih,scale=1080:1920', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '18', '-c:a', 'aac', '-b:a', '128k', temp_output], job_id, progress[job_id])
            elif func == 'ratio_square':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', 'crop=min(iw\,ih):min(iw\,ih),scale=1080:1080', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '18', '-c:a', 'aac', '-b:a', '128k', temp_output], job_id, progress[job_id])
            elif func == 'ratio_fb':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', 'scale=1080:1350', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '18', temp_output], job_id, progress[job_id])
            elif func == 'ratio_twitter':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', 'scale=1280:720', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '18', temp_output], job_id, progress[job_id])
            elif func == 'ratio_pinterest':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', 'scale=1000:1500', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '18', temp_output], job_id, progress[job_id])
            elif func == 'ratio_linkedin':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', 'scale=1920:1080', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '18', temp_output], job_id, progress[job_id])
            elif func == 'crop_center':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', 'crop=min(iw\,ih):min(iw\,ih)', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '18', temp_output], job_id, progress[job_id])
            
            # BLOQUE 3: BYPASS (PRO)
            elif func == 'bypass_wa':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '23', '-vf', 'scale=1280:720', '-c:a', 'aac', '-b:a', '64k', '-movflags', '+faststart', temp_output], job_id, progress[job_id])
            elif func == 'bypass_tg':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '18', '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart+frag_keyframe+empty_moov', '-brand', 'mp42', '-map_metadata', '-1', temp_output], job_id, progress[job_id])
            elif func == 'bypass_discord':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28', '-vf', 'scale=1280:720', '-c:a', 'aac', '-b:a', '48k', temp_output], job_id, progress[job_id])
            elif func == 'bypass_email':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '30', '-vf', 'scale=640:480', '-c:a', 'aac', '-b:a', '32k', temp_output], job_id, progress[job_id])
            elif func == 'target_50mb':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28', '-fs', '50M', '-c:a', 'aac', '-b:a', '64k', temp_output], job_id, progress[job_id])
            elif func == 'target_10mb':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '35', '-fs', '10M', '-c:a', 'aac', '-b:a', '32k', temp_output], job_id, progress[job_id])
            elif func == 'strip_meta':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-c', 'copy', '-map_metadata', '-1', temp_output], job_id, progress[job_id])
            elif func == 'remove_gps':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-c', 'copy', '-map_metadata', '-1', '-map_metadata:s:v', '-1', '-map_metadata:s:a', '-1', temp_output], job_id, progress[job_id])
            elif func == 'compress_lossless':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', '-c:a', 'aac', '-b:a', '192k', temp_output], job_id, progress[job_id])
            elif func == 'fast_start':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-c', 'copy', '-movflags', '+faststart', temp_output], job_id, progress[job_id])
            
            # BLOQUE 4: AUDIO (PRO)
            elif func == 'audio_boost_200':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-af', 'volume=2.0', '-c:v', 'copy', temp_output], job_id, progress[job_id])
            elif func == 'audio_boost_300':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-af', 'volume=3.0', '-c:v', 'copy', temp_output], job_id, progress[job_id])
            elif func == 'bass_boost':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-af', 'equalizer=f=100:t=q:w=1:g=5,equalizer=f=200:t=q:w=1:g=3', '-c:v', 'copy', temp_output], job_id, progress[job_id])
            elif func == 'clean_noise':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-af', 'highpass=f=200,lowpass=f=3000,afftdn=nr=10:nf=-25', '-c:v', 'copy', temp_output], job_id, progress[job_id])
            elif func == 'normalize_audio':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11', '-c:v', 'copy', temp_output], job_id, progress[job_id])
            elif func == 'isolate_voice':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-af', 'highpass=f=300,lowpass=f=3400', '-c:v', 'copy', temp_output], job_id, progress[job_id])
            elif func == 'remove_voice':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-af', 'pan=mono|c0=c0', '-c:v', 'copy', temp_output], job_id, progress[job_id])
            elif func == 'audio_stereo':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-af', 'stereotools=mode=ms', '-c:v', 'copy', temp_output], job_id, progress[job_id])
            elif func == 'audio_8d':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-af', 'chorus=0.7:0.9:55:0.4:0.25:2', '-c:v', 'copy', temp_output], job_id, progress[job_id])
            elif func == 'mute_low_db':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-af', 'silenceremove=start_periods=1:start_threshold=-50dB', '-c:v', 'copy', temp_output], job_id, progress[job_id])
            
            # BLOQUE 5: REPARACION (PRO)
            elif func == 'repair_index':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-c', 'copy', '-fflags', '+genpts', temp_output], job_id, progress[job_id])
            elif func == 'fix_sync':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-c:v', 'copy', '-c:a', 'aac', '-af', 'adelay=0|0', temp_output], job_id, progress[job_id])
            elif func == 'reencode_h264':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '18', '-c:a', 'aac', '-b:a', '128k', temp_output], job_id, progress[job_id])
            elif func == 'fix_green_screen':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', 'eq=brightness=0.05:saturation=1.2', '-c:a', 'copy', temp_output], job_id, progress[job_id])
            elif func == 'convert_8bit':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-pix_fmt', 'yuv420p', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '18', temp_output], job_id, progress[job_id])
            elif func == 'remove_b_frames':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-c:v', 'libx264', '-bf', '0', '-preset', 'ultrafast', '-crf', '18', temp_output], job_id, progress[job_id])
            elif func == 'force_aac':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-c:v', 'copy', '-c:a', 'aac', '-b:a', '128k', temp_output], job_id, progress[job_id])
            elif func == 'fix_aspect_ratio':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', 'setdar=16/9', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '18', temp_output], job_id, progress[job_id])
            elif func == 'repair_moov':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-c', 'copy', '-movflags', '+faststart', temp_output], job_id, progress[job_id])
            elif func == 'clean_keyframes':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-c:v', 'libx264', '-g', '30', '-keyint_min', '30', '-preset', 'ultrafast', '-crf', '18', temp_output], job_id, progress[job_id])
            
            # BLOQUE 6: RENDERIZADO (PRO)
            elif func == 'upscale_1080':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', 'scale=1920:1080:flags=lanczos', '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', '-c:a', 'aac', '-b:a', '128k', temp_output], job_id, progress[job_id])
            elif func == 'upscale_4k':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', 'scale=3840:2160:flags=lanczos', '-c:v', 'libx264', '-crf', '16', '-preset', 'ultrafast', '-c:a', 'aac', '-b:a', '192k', temp_output], job_id, progress[job_id])
            elif func == 'fps_60':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', 'minterpolate=fps=60:mi_mode=dup', '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', '-c:a', 'aac', '-b:a', '128k', temp_output], job_id, progress[job_id])
            elif func == 'fps_custom':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', f'minterpolate=fps={fps}:mi_mode=dup', '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', '-c:a', 'aac', '-b:a', '128k', temp_output], job_id, progress[job_id])
            elif func == 'sharpen':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', 'unsharp=5:5:1.5:5:5:1.0', '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', temp_output], job_id, progress[job_id])
            elif func == 'denoise_clipping':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', 'pp=de', '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', temp_output], job_id, progress[job_id])
            elif func == 'stabilize_ai':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', 'deshake', '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', temp_output], job_id, progress[job_id])
            elif func == 'hdr_simulation':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', 'eq=contrast=1.2:brightness=0.05:saturation=1.3', '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', temp_output], job_id, progress[job_id])
            elif func == 'deinterlace':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', 'yadif', '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', temp_output], job_id, progress[job_id])
            elif func == 'brighten_dark':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', 'eq=brightness=0.2', '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', temp_output], job_id, progress[job_id])
            
            # BLOQUE 7: EFECTOS VISUALES (PRO)
            elif func == 'fx_cyberpunk':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', 'eq=brightness=0.1:contrast=1.3:saturation=2:gamma=1.5', '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', temp_output], job_id, progress[job_id])
            elif func == 'fx_vhs':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', 'curves=vintage,noise=alls=10:allf=t', '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', temp_output], job_id, progress[job_id])
            elif func == 'fx_cinema_bars':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', 'crop=iw:iw/2.35,scale=1920:816,pad=1920:1080:0:132', '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', temp_output], job_id, progress[job_id])
            elif func == 'fx_bw':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', 'hue=s=0', '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', temp_output], job_id, progress[job_id])
            elif func == 'fx_sepia':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', 'colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131', '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', temp_output], job_id, progress[job_id])
            elif func == 'fx_invert':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', 'negate', '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', temp_output], job_id, progress[job_id])
            elif func == 'fx_blur_edges':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', "split[original][copy];[copy]scale=ih*9/16:ih,gblur=sigma=20[blurred];[blurred][original]overlay=(main_w-overlay_w)/2:(main_h-overlay_h)/2", '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', temp_output], job_id, progress[job_id])
            elif func == 'fx_vignette':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', 'vignette=PI/4', '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', temp_output], job_id, progress[job_id])
            elif func == 'fx_glitch':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', 'noise=alls=50:allf=t', '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', temp_output], job_id, progress[job_id])
            elif func == 'fx_saturate':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', 'eq=saturation=2.5', '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', temp_output], job_id, progress[job_id])
            
            # BLOQUE 8: EDICION AVANZADA (PRO)
            elif func == 'del_watermark':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', 'delogo=x=10:y=10:w=100:h=50', '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', temp_output], job_id, progress[job_id])
            elif func == 'extract_frames':
                temp_output = temp_output.replace('.mp4', '.zip')
                os.makedirs(f'uploads/frames_{job_id}', exist_ok=True)
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', 'fps=1', f'uploads/frames_{job_id}/frame_%04d.png'], job_id, progress[job_id])
                subprocess.run(['zip', '-r', temp_output, f'uploads/frames_{job_id}'], check=True)
            elif func == 'slowmo_smooth':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', 'minterpolate=fps=60:mi_mode=mci', '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', '-c:a', 'aac', '-b:a', '128k', temp_output], job_id, progress[job_id])
            elif func == 'speed_4x':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', 'setpts=0.25*PTS', '-af', 'atempo=4.0', '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', temp_output], job_id, progress[job_id])
            elif func == 'add_fade_in':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', 'fade=in:0:30', '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', temp_output], job_id, progress[job_id])
            elif func == 'add_fade_out':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', 'fade=out:st=0:d=30', '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', temp_output], job_id, progress[job_id])
            elif func == 'remove_first_3s':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-ss', '3', '-c', 'copy', temp_output], job_id, progress[job_id])
            elif func == 'remove_last_3s':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-ss', '0', '-t', '30', '-c', 'copy', temp_output], job_id, progress[job_id])
            elif func == 'zoom_in_static':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', 'scale=iw*1.15:ih*1.15,crop=iw/1.15:ih/1.15', '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', temp_output], job_id, progress[job_id])
            elif func == 'chroma_key':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vf', 'chromakey=0x00FF00:0.1:0.2', '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', temp_output], job_id, progress[job_id])
            
            # BLOQUE 9: CONVERSORES (PRO)
            elif func == 'to_mp4_clean':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '18', '-c:a', 'aac', '-b:a', '128k', temp_output], job_id, progress[job_id])
            elif func == 'to_webm':
                temp_output = temp_output.replace('.mp4', '.webm')
                run_ffmpeg(['ffmpeg', '-i', current_input, '-c:v', 'libvpx', '-b:v', '1M', '-c:a', 'libvorbis', temp_output], job_id, progress[job_id])
            elif func == 'to_mkv':
                temp_output = temp_output.replace('.mp4', '.mkv')
                run_ffmpeg(['ffmpeg', '-i', current_input, '-c', 'copy', temp_output], job_id, progress[job_id])
            elif func == 'to_mov':
                temp_output = temp_output.replace('.mp4', '.mov')
                run_ffmpeg(['ffmpeg', '-i', current_input, '-c', 'copy', temp_output], job_id, progress[job_id])
            elif func == 'to_avi':
                temp_output = temp_output.replace('.mp4', '.avi')
                run_ffmpeg(['ffmpeg', '-i', current_input, '-c:v', 'libx264', '-c:a', 'mp3', temp_output], job_id, progress[job_id])
            elif func == 'to_flv':
                temp_output = temp_output.replace('.mp4', '.flv')
                run_ffmpeg(['ffmpeg', '-i', current_input, '-c:v', 'libx264', '-c:a', 'aac', temp_output], job_id, progress[job_id])
            elif func == 'to_ogv':
                temp_output = temp_output.replace('.mp4', '.ogv')
                run_ffmpeg(['ffmpeg', '-i', current_input, '-c:v', 'libtheora', '-c:a', 'libvorbis', temp_output], job_id, progress[job_id])
            elif func == 'to_mp3_high':
                temp_output = temp_output.replace('.mp4', '.mp3')
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vn', '-c:a', 'libmp3lame', '-b:a', '320k', temp_output], job_id, progress[job_id])
            elif func == 'to_wav':
                temp_output = temp_output.replace('.mp4', '.wav')
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vn', '-c:a', 'pcm_s16le', temp_output], job_id, progress[job_id])
            elif func == 'to_flac':
                temp_output = temp_output.replace('.mp4', '.flac')
                run_ffmpeg(['ffmpeg', '-i', current_input, '-vn', '-c:a', 'flac', temp_output], job_id, progress[job_id])
            
            # BLOQUE 10: BITRATE Y PARAMETROS (PRO)
            elif func == 'bitrate_1k':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-c:v', 'libx264', '-b:v', '1M', '-preset', 'ultrafast', '-c:a', 'aac', '-b:a', '64k', temp_output], job_id, progress[job_id])
            elif func == 'bitrate_5k':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-c:v', 'libx264', '-b:v', '5M', '-preset', 'ultrafast', '-c:a', 'aac', '-b:a', '128k', temp_output], job_id, progress[job_id])
            elif func == 'bitrate_12k':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-c:v', 'libx264', '-b:v', '12M', '-preset', 'ultrafast', '-c:a', 'aac', '-b:a', '192k', temp_output], job_id, progress[job_id])
            elif func == 'gop_set':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-c:v', 'libx264', '-g', '60', '-preset', 'ultrafast', '-crf', '18', temp_output], job_id, progress[job_id])
            elif func == 'audio_48khz':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-c:v', 'copy', '-c:a', 'aac', '-ar', '48000', temp_output], job_id, progress[job_id])
            elif func == 'audio_44khz':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-c:v', 'copy', '-c:a', 'aac', '-ar', '44100', temp_output], job_id, progress[job_id])
            elif func == 'pixel_yuv420p':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-pix_fmt', 'yuv420p', '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', temp_output], job_id, progress[job_id])
            elif func == 'strip_subtitles':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-c', 'copy', '-sn', temp_output], job_id, progress[job_id])
            elif func == 'tune_zerolatency':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-c:v', 'libx264', '-tune', 'zerolatency', '-preset', 'ultrafast', '-crf', '18', temp_output], job_id, progress[job_id])
            elif func == 'optimize_static_image':
                run_ffmpeg(['ffmpeg', '-i', current_input, '-c:v', 'libx264', '-g', '9999', '-keyint_min', '9999', '-preset', 'ultrafast', '-crf', '18', temp_output], job_id, progress[job_id])
            
            else:
                # Funcion no reconocida, copiar sin cambios
                run_ffmpeg(['ffmpeg', '-i', current_input, '-c', 'copy', temp_output], job_id, progress[job_id])
            
            # Actualizar entrada para la siguiente funcion
            if os.path.exists(temp_output):
                if current_input != input_path and os.path.exists(current_input):
                    os.remove(current_input)
                current_input = temp_output
                
        except Exception as e:
            print(f"Error processing {func}: {e}")
            continue
    
    # Mover resultado final
    if current_input != output_path:
        subprocess.run(['mv', current_input, output_path], check=True)
    
    # Limpiar archivos temporales
    for f in os.listdir('uploads'):
        if f.startswith(f'temp_{job_id}') or f.startswith(f'{job_id}_input'):
            try: os.remove(os.path.join('uploads', f))
            except: pass
    
    progress[job_id] = 100

@app.route('/progress/<job_id>')
def get_progress(job_id):
    return jsonify({'progress': progress.get(job_id, 0)})

@app.route('/download/<job_id>')
def download(job_id):
    for f in os.listdir('processed'):
        if f.startswith(f'processed_{job_id}'):
            ext = f.rsplit('.', 1)[-1]
            return send_file(f'processed/{f}', as_attachment=True, download_name=f"videopro_{job_id}.{ext}")
    return jsonify({'error': 'Archivo expirado'}), 404

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form['user'] == ADMIN_USER and request.form['pass'] == ADMIN_PASS:
            session['logged_in'] = True
            return redirect(url_for('admin_panel'))
        return render_template('admin.html', error='Credenciales incorrectas', login=True)
    return render_template('admin.html', login=True)

@app.route('/admin')
@login_required
def admin_panel():
    s = load_stats()
    most = max(s['functions_used'], key=s['functions_used'].get) if s['functions_used'] else 'Ninguna'
    peak = max(s['visits_by_hour'], key=s['visits_by_hour'].get) if s['visits_by_hour'] else 'N/A'
    return render_template('admin.html', stats=s, most_used=most, peak_hour=peak, total_users=len(s['users_ip']), login=False)

@app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect(url_for('admin_login'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000, threaded=True)