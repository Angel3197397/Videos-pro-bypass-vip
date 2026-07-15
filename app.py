from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, session
import subprocess, os, uuid, threading, json
from datetime import datetime
import functools

app = Flask(__name__)
app.secret_key = 'videopro_2024_secret'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['PROCESSED_FOLDER'] = 'processed'
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024

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
    
    options = {
        'function': request.form.get('function'),
        'fps': request.form.get('fps'),
        'format': request.form.get('format'),
        'speed': request.form.get('speed'),
    }
    
    s = load_stats()
    s['total_videos'] += 1
    func = options.get('function', 'desconocido')
    s['functions_used'][func] = s['functions_used'].get(func, 0) + 1
    s['history'].append({'job_id': job_id, 'time': datetime.now().strftime('%H:%M:%S'), 'function': func, 'filename': file.filename[:25]})
    if len(s['history']) > 50: s['history'] = s['history'][-50:]
    save_stats(s)
    
    output_path = f"processed/processed_{job_id}.mp4"
    threading.Thread(target=process_video, args=(input_path, output_path, options, job_id)).start()
    return jsonify({'job_id': job_id})

def process_video(input_path, output_path, options, job_id):
    global progress
    progress[job_id] = 0
    func = options.get('function')
    cmd = ['ffmpeg', '-i', input_path]
    
    if func == 'vypeo':
        cmd = ['ffmpeg', '-i', input_path, '-c', 'copy', output_path]
    elif func == 'boost_fps':
        fps = options.get('fps', '60')
        cmd = ['ffmpeg', '-i', input_path, '-vf', f'minterpolate=fps={fps}:mi_mode=dup', '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', '-threads', '0', '-c:a', 'aac', '-b:a', '128k', output_path]
    elif func == 'upscale_4k':
        cmd = ['ffmpeg', '-i', input_path, '-vf', 'scale=3840:2160:flags=lanczos', '-c:v', 'libx264', '-crf', '16', '-preset', 'ultrafast', '-threads', '0', '-c:a', 'aac', '-b:a', '192k', output_path]
    elif func == 'upscale_1080p':
        cmd = ['ffmpeg', '-i', input_path, '-vf', 'scale=1920:1080:flags=lanczos', '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', '-threads', '0', '-c:a', 'aac', '-b:a', '128k', output_path]
    elif func == 'reduce_noise':
        cmd = ['ffmpeg', '-i', input_path, '-vf', 'hqdn3d=4:3:6:4.5', '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', '-threads', '0', '-c:a', 'aac', '-b:a', '128k', output_path]
    elif func == 'stabilize':
        subprocess.run(['ffmpeg', '-i', input_path, '-vf', 'vidstabdetect=shakiness=10:result=transforms.trf', '-f', 'null', '-'], check=True)
        progress[job_id] = 40
        cmd = ['ffmpeg', '-i', input_path, '-vf', 'vidstabtransform=smoothing=30:input=transforms.trf', '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', '-threads', '0', '-c:a', 'aac', '-b:a', '128k', output_path]
    elif func == 'brighten':
        cmd = ['ffmpeg', '-i', input_path, '-vf', 'eq=brightness=0.15', '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', '-threads', '0', '-c:a', 'aac', '-b:a', '128k', output_path]
    elif func == 'format_tiktok':
        cmd = ['ffmpeg', '-i', input_path, '-vf', 'crop=ih*9/16:ih,scale=1080:1920', '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', '-threads', '0', '-c:a', 'aac', '-b:a', '128k', output_path]
    elif func == 'format_reels':
        cmd = ['ffmpeg', '-i', input_path, '-vf', 'crop=min(iw\,ih):min(iw\,ih),scale=1080:1080', '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', '-threads', '0', '-c:a', 'aac', '-b:a', '128k', output_path]
    elif func == 'format_youtube':
        cmd = ['ffmpeg', '-i', input_path, '-vf', 'scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2', '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', '-threads', '0', '-c:a', 'aac', '-b:a', '192k', output_path]
    elif func == 'bypass_telegram':
        cmd = ['ffmpeg', '-i', input_path, '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '18', '-threads', '0', '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart+frag_keyframe+empty_moov', '-fflags', '+genpts', '-brand', 'mp42', '-map_metadata', '-1', output_path]
    elif func == 'bypass_whatsapp':
        cmd = ['ffmpeg', '-i', input_path, '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '23', '-threads', '0', '-c:a', 'aac', '-b:a', '64k', '-vf', 'scale=1280:720', '-movflags', '+faststart', output_path]
    elif func == 'compress':
        cmd = ['ffmpeg', '-i', input_path, '-c:v', 'libx264', '-crf', '28', '-preset', 'ultrafast', '-threads', '0', '-c:a', 'aac', '-b:a', '64k', output_path]
    elif func == 'clean_audio':
        cmd = ['ffmpeg', '-i', input_path, '-af', 'highpass=f=200,lowpass=f=3000,afftdn=nr=10:nf=-25', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '128k', output_path]
    elif func == 'extract_mp3':
        output_path = output_path.replace('.mp4', '.mp3')
        cmd = ['ffmpeg', '-i', input_path, '-vn', '-c:a', 'libmp3lame', '-b:a', '320k', output_path]
    elif func == 'slow_motion':
        cmd = ['ffmpeg', '-i', input_path, '-vf', 'setpts=2*PTS', '-filter:a', 'atempo=0.5', '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', '-threads', '0', '-c:a', 'aac', '-b:a', '128k', output_path]
    elif func == 'cinema':
        cmd = ['ffmpeg', '-i', input_path, '-vf', 'crop=iw:iw/2.35,scale=1920:816,pad=1920:1080:0:132,eq=contrast=1.1:saturation=1.2', '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', '-threads', '0', '-c:a', 'aac', '-b:a', '192k', output_path]
    elif func == 'reverse':
        cmd = ['ffmpeg', '-i', input_path, '-vf', 'reverse', '-af', 'areverse', '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', '-threads', '0', '-c:a', 'aac', '-b:a', '128k', output_path]
    elif func == 'gif':
        output_path = output_path.replace('.mp4', '.gif')
        cmd = ['ffmpeg', '-i', input_path, '-vf', 'fps=15,scale=480:-1', '-c:v', 'gif', output_path]
    elif func == 'remove_metadata':
        cmd = ['ffmpeg', '-i', input_path, '-c', 'copy', '-map_metadata', '-1', output_path]
    else:
        cmd = ['ffmpeg', '-i', input_path, '-c:v', 'libx264', '-crf', '18', '-preset', 'ultrafast', '-threads', '0', '-c:a', 'aac', '-b:a', '128k', output_path]
    
    progress[job_id] = 50
    subprocess.run(cmd, check=True)
    progress[job_id] = 100

@app.route('/progress/<job_id>')
def get_progress(job_id):
    return jsonify({'progress': progress.get(job_id, 0)})

@app.route('/download/<job_id>')
def download(job_id):
    for f in os.listdir('processed'):
        if f.startswith(f'processed_{job_id}'):
            return send_file(f'processed/{f}', as_attachment=True, download_name=f"videopro_{job_id}.{f.rsplit('.',1)[-1]}")
    return jsonify({'error': 'Expirado'}), 404

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form['user'] == ADMIN_USER and request.form['pass'] == ADMIN_PASS:
            session['logged_in'] = True
            return redirect(url_for('admin_panel'))
        return render_template('admin.html', error='Mal', login=True)
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