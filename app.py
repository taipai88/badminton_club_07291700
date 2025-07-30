from flask import Flask, render_template, request, redirect, url_for, flash, session, make_response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import datetime
import csv
import io

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_super_secret_key_here' # 請替換為您自己的秘密金鑰
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///badminton_club.db' # SQLite 資料庫檔案
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# 全局變數，用於追蹤目前登入人數 (簡單示範，重啟伺服器會重置，非生產環境最佳實踐)
app.logged_in_users_count = 0

# --- 資料庫模型定義 ---
class User(db.Model):
    # 'id' 是資料庫的內部主鍵，自動遞增，用於內部關聯和識別。
    # 當我們在 session 中儲存 user_id 時，儲存的是這個 'id'。
    id = db.Column(db.Integer, primary_key=True)
    
    # 'member_id' 是用戶的手機號碼，作為用戶登入的唯一識別符。
    # 它是用戶層面的「會員ID」。
    member_id = db.Column(db.String(10), unique=True, nullable=False) 
    username = db.Column(db.String(80), unique=True, nullable=False) # 用戶名，用於顯示和唯一性
    # 郵箱欄位：不唯一，允許為空
    email = db.Column(db.String(120), unique=False, nullable=True) 
    password_hash = db.Column(db.String(128), nullable=False)
    
    # 會員資料欄位
    gender = db.Column(db.String(10), default='男') # 性別
    address = db.Column(db.String(200)) # 住家地址

    membership_type = db.Column(db.String(20), default='臨打') # 會員等級 (年繳, 季繳, 月繳, 臨打)
    badminton_level = db.Column(db.Integer, default=1) # 羽球等級 (1-18級)

    is_admin = db.Column(db.Boolean, default=False) # 是否為管理員

    def set_password(self, password):
        """設定用戶密碼，使用哈希加密"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """檢查輸入密碼是否與儲存的哈希值匹配"""
        return check_password_hash(self.password_hash, password)

    @property
    def formatted_member_id(self):
        """格式化 member_id (手機號碼) 為 09XX-XXX-XXX 格式以供顯示"""
        if self.member_id and len(self.member_id) == 10 and self.member_id.isdigit():
            return f"{self.member_id[:4]}-{self.member_id[4:7]}-{self.member_id[7:]}"
        return self.member_id # 如果不符合10位數字，則返回原始值

    def __repr__(self):
        """物件的字串表示，用於調試"""
        return f'<User {self.username}>'

class Court(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False) # 球場名稱（現在是球隊名稱）
    description = db.Column(db.String(200)) # 球場描述

    def __repr__(self):
        """物件的字串表示，用於調試"""
        return f'<Court {self.name}>'

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # 'user_id' 是外鍵，指向 User 模型的 'id' (主鍵)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False) # 預約用戶ID
    court_id = db.Column(db.Integer, db.ForeignKey('court.id'), nullable=False) # 預約球場ID
    booking_date = db.Column(db.Date, nullable=False) # 活動日期
    start_time = db.Column(db.Time, nullable=False) # 開始時間
    end_time = db.Column(db.Time, nullable=False) # 結束時間
    status = db.Column(db.String(50), default='已預約') # 預約狀態
    creation_date = db.Column(db.DateTime, nullable=False, default=datetime.datetime.now) # 預約建檔日期時間
    time_slot_category = db.Column(db.String(10), nullable=False) # 預約時段類別 (上午/下午/晚上)

    user = db.relationship('User', backref=db.backref('bookings', lazy=True)) # 與 User 模型的關聯
    court = db.relationship('Court', backref=db.backref('bookings', lazy=True)) # 與 Court 模型的關聯

    def __repr__(self):
        """物件的字串表示，用於調試"""
        return f'<Booking {self.user.username} - {self.court.name} - {self.booking_date} {self.start_time}-{self.end_time}>'

# 上下文處理器：使 logged_in_users_count 在所有模板中可用
@app.context_processor
def inject_global_vars():
    return dict(logged_in_users_count=app.logged_in_users_count)

# --- 資料庫創建和初始數據填充函數 ---
def create_tables_and_initial_data():
    """
    創建資料庫表格並填充初始數據，包括預設球場和管理員帳號。
    此函數應在應用程式啟動時呼叫一次。
    """
    with app.app_context(): # 確保在應用程式上下文中執行資料庫操作
        db.create_all() # 創建所有未存在的表格

        # 確保 '大智羽球隊' 存在，如果不存在則創建
        court_dazhi = Court.query.filter_by(name='大智羽球隊').first()
        if not court_dazhi:
            db.session.add(Court(name='大智羽球隊', description='標準羽毛球場'))
            print("Created '大智羽球隊'.")
        else:
            # 如果存在，確保描述正確
            if court_dazhi.description != '標準羽毛球場':
                court_dazhi.description = '標準羽毛球場'
                print("Updated description for '大智羽球隊'.")

        # 確保 '樂樂羽球隊' 存在，如果不存在則創建
        court_lele = Court.query.filter_by(name='樂樂羽球隊').first()
        if not court_lele:
            db.session.add(Court(name='樂樂羽球隊', description='木質地板，靠近窗戶'))
            print("Created '樂樂羽球隊'.")
        else:
            # 如果存在，確保描述正確
            if court_lele.description != '木質地板，靠近窗戶':
                court_lele.description = '木質地板，靠近窗戶'
                print("Updated description for '樂樂羽球隊'.")

        # --- 設定一組預設管理員帳號 ---
        admin_member_id = '0909879989' # 管理員的登入手機號碼 (member_id)
        admin_username = 'admin'      # 管理員的用戶名
        admin_password = '123'        # 管理員的密碼 (請在實際部署時務必修改為更安全的密碼！)

        admin_user = User.query.filter_by(member_id=admin_member_id).first()

        if not admin_user:
            # 如果管理員帳號不存在，則創建它
            new_admin_user = User(
                member_id=admin_member_id, # 使用 member_id 進行查詢和創建
                username=admin_username,
                email='admin@example.com', # 管理員郵箱 (可選)
                gender='男', 
                address='管理員地址', 
                membership_type='年繳', 
                badminton_level=18, 
                is_admin=True
            )
            new_admin_user.set_password(admin_password) # 設定加密後的密碼
            db.session.add(new_admin_user)
            print(f"Created default admin user: {admin_username} (Member ID: {admin_member_id})")
        else:
            # 如果管理員帳號已存在，確保它是管理員，並更新其用戶名和密碼
            if not admin_user.is_admin:
                admin_user.is_admin = True
                print(f"Updated existing user {admin_member_id} to be an admin.")
            if admin_user.username != admin_username:
                admin_user.username = admin_username
                print(f"Updated username for admin user {admin_member_id} to: {admin_username}")
            if not admin_user.check_password(admin_password): # 檢查並更新密碼
                admin_user.set_password(admin_password)
                print(f"Updated password for admin user: {admin_member_id}")
        # --- 管理員帳號設定結束 ---

        db.session.commit() # 提交所有資料庫變更

# --- 定義預約時段 ---
TIME_SLOTS = {
    '上午': {'start': datetime.time(8, 0), 'end': datetime.time(12, 0)},
    '下午': {'start': datetime.time(12, 0), 'end': datetime.time(17, 0)},
    '晚上': {'start': datetime.time(17, 0), 'end': datetime.time(22, 0)}
}

# --- 定義下拉選單選項 ---
GENDER_OPTIONS = ['男', '女']
MEMBERSHIP_TYPE_OPTIONS = ['年繳', '季繳', '月繳', '臨打']
BADMINTON_LEVEL_OPTIONS = list(range(1, 19)) # 羽球等級範圍 1 到 18

# --- 路由與視圖函數 ---

@app.route('/')
def index():
    """首頁路由"""
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """會員註冊路由"""
    if request.method == 'POST':
        member_id = request.form['member_id'] # 用戶輸入的手機號碼 (member_id)
        username = request.form['username']
        email = request.form['email']
        if email == '': # 將空字串郵箱轉換為 None 以便資料庫儲存
            email = None
        password = request.form['password']
        gender = request.form['gender']
        address = request.form['address']
        membership_type = request.form['membership_type']
        badminton_level = int(request.form['badminton_level']) # 轉換為整數

        # 後端驗證 member_id (手機號碼) 格式
        if not (len(member_id) == 10 and member_id.isdigit()):
            flash('手機號碼格式不正確，請輸入10位數字。', 'danger')
            return redirect(url_for('register'))
        
        # 檢查 member_id (手機號碼) 和 用戶名 是否已存在
        existing_member_id = User.query.filter_by(member_id=member_id).first()
        existing_username = User.query.filter_by(username=username).first()

        if existing_member_id:
            flash('此手機號碼已被註冊！', 'danger')
        elif existing_username:
            flash('用戶名已被使用！', 'danger')
        else:
            new_user = User(
                member_id=member_id, # 將手機號碼儲存為 member_id
                username=username,
                email=email, 
                gender=gender,
                address=address,
                membership_type=membership_type,
                badminton_level=badminton_level
            )
            new_user.set_password(password) # 設定加密後的密碼
            db.session.add(new_user)
            db.session.commit()
            flash('註冊成功！請登入。', 'success')
            
            # 註冊成功後自動登入
            # 在 session 中儲存的是用戶的內部主鍵 'id'
            session['user_id'] = new_user.id 
            session['username'] = new_user.username
            session['is_admin'] = new_user.is_admin
            app.logged_in_users_count += 1 # 註冊成功並自動登入，增加計數
            return redirect(url_for('dashboard'))
    
    # GET 請求時，傳遞下拉選單選項到模板
    return render_template(
        'register.html',
        gender_options=GENDER_OPTIONS,
        membership_type_options=MEMBERSHIP_TYPE_OPTIONS,
        badminton_level_options=BADMINTON_LEVEL_OPTIONS
    )

@app.route('/login', methods=['GET', 'POST'])
def login():
    """會員登入路由"""
    if request.method == 'POST':
        member_id = request.form['member_id'] # 登入使用用戶輸入的手機號碼 (member_id)
        password = request.form['password']
        user = User.query.filter_by(member_id=member_id).first() # 根據 member_id 查詢用戶

        current_time_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S') 

        if user and user.check_password(password):
            # 修正登入人數計數邏輯：只有當用戶 ID 不在 session 中，或者與當前 session 的用戶 ID 不同時才增加
            if 'user_id' not in session or session['user_id'] != user.id:
                app.logged_in_users_count += 1 # 登入成功，增加計數

            session['user_id'] = user.id
            session['username'] = user.username 
            session['is_admin'] = user.is_admin
            
            flash(f'{current_time_str} - 歡迎回來, {user.username}！', 'success') 
            return redirect(url_for('dashboard'))
        else:
            flash(f'{current_time_str} - 手機號碼或密碼不正確。', 'danger') 
    return render_template('login.html')

@app.route('/logout')
def logout():
    """登出路由"""
    # 只有當用戶確實登入時才減少計數
    if 'user_id' in session: 
        app.logged_in_users_count -= 1
    session.pop('user_id', None)
    session.pop('username', None)
    session.pop('is_admin', None)
    flash('您已登出。', 'info')
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    """用戶儀表板路由"""
    if 'user_id' not in session:
        flash('請先登入。', 'warning')
        return redirect(url_for('login'))
    
    # 從 session 中獲取用戶的內部主鍵 'id'
    user = User.query.get(session['user_id']) 
    # 查詢該用戶的所有預約，並進行排序
    user_bookings = Booking.query.filter_by(user_id=session['user_id']).order_by(
        Booking.booking_date.asc(), 
        Booking.court_id.asc(),     
        Booking.start_time.asc()    
    ).all()
    
    return render_template('dashboard.html', user=user, bookings=user_bookings)

@app.route('/book_court', methods=['GET', 'POST']) 
def book_court():
    """預約場地路由"""
    if 'user_id' not in session:
        flash('請先登入才能預約場地。', 'warning')
        return redirect(url_for('login'))
    
    courts = Court.query.all() 
    
    if request.method == 'POST':
        court_id = request.form['court_id']
        booking_date_str = request.form['booking_date']
        selected_slot_name = request.form['time_slot'] 

        try:
            booking_date = datetime.datetime.strptime(booking_date_str, '%Y-%m-%d').date()
            if selected_slot_name in TIME_SLOTS:
                start_time = TIME_SLOTS[selected_slot_name]['start']
                end_time = TIME_SLOTS[selected_slot_name]['end']
            else:
                flash('無效的預約時段。', 'danger')
                return redirect(url_for('book_court'))

        except ValueError:
            flash('日期格式不正確。', 'danger')
            return redirect(url_for('book_court'))

        # --- 重複預約檢查邏輯 (新增 user_id 條件) ---
        # 檢查該用戶是否已在該球場、該日期、該時段有預約
        existing_booking = Booking.query.filter_by(
            user_id=session['user_id'], # 篩選當前登入用戶的預約
            court_id=court_id,
            booking_date=booking_date,
            # 檢查時間段是否重疊
        ).filter(
            db.or_(
                # 情況1: 新預約的開始時間落在現有預約區間內
                db.and_(Booking.start_time >= start_time, Booking.start_time < end_time),
                # 情況2: 新預約的結束時間落在現有預約區間內
                db.and_(Booking.end_time > start_time, Booking.end_time <= end_time),
                # 情況3: 現有預約的開始時間等於或早於新預約的開始時間，且現有預約的結束時間等於或晚於新預約的結束時間 (現有預約完全包含新預約)
                db.and_(Booking.start_time <= start_time, Booking.end_time >= end_time),
                # 情況4: 新預約的時段完全包含現有預約的時段
                db.and_(start_time <= Booking.start_time, end_time >= Booking.end_time)
            )
        ).first()

        if existing_booking:
            flash('! 已預約不可重複', 'danger') # 顯示新的錯誤訊息
            return redirect(url_for('book_court'))
        # --- 結束重複預約檢查邏輯 ---

        new_booking = Booking(
            user_id=session['user_id'], # 使用 session 中儲存的用戶 'id' 作為外鍵
            court_id=court_id,
            booking_date=booking_date,
            start_time=start_time,
            end_time=end_time,
            time_slot_category=selected_slot_name 
        )
        db.session.add(new_booking)
        db.session.commit()
        flash(f'{selected_slot_name} 時段場地預約成功！', 'success')
        return redirect(url_for('dashboard'))

    today = datetime.date.today()
    slot_names = list(TIME_SLOTS.keys())
    return render_template('book_court.html', courts=courts, today=today, time_slots=slot_names)

# --- 管理員功能 ---
@app.route('/admin/users')
def admin_users():
    """管理員：所有會員列表頁面"""
    if 'user_id' not in session or not session['is_admin']:
        flash('您沒有權限訪問此頁面。', 'danger')
        return redirect(url_for('index')) # 更改重定向目標為 index
    
    users = User.query.all() 
    return render_template('admin_users.html', users=users)

@app.route('/admin/add_user', methods=['GET', 'POST'])
def add_user():
    """管理員：新增會員頁面"""
    if 'user_id' not in session or not session['is_admin']:
        flash('您沒有權限訪問此頁面。', 'danger')
        return redirect(url_for('index'))

    if request.method == 'POST':
        member_id = request.form['member_id'].strip()
        username = request.form['username'].strip()
        email = request.form['email'].strip()
        if email == '':
            email = None
        password = request.form['password']
        gender = request.form['gender']
        address = request.form['address'].strip()
        membership_type = request.form['membership_type']
        badminton_level = int(request.form['badminton_level'])
        is_admin = True if request.form.get('is_admin') == 'on' else False

        # 後端驗證 member_id (手機號碼) 格式
        if not (len(member_id) == 10 and member_id.isdigit()):
            flash('手機號碼格式不正確，請輸入10位數字。', 'danger')
            return redirect(url_for('add_user'))
        
        # 檢查 member_id 和 username 是否已存在
        existing_member_id = User.query.filter_by(member_id=member_id).first()
        existing_username = User.query.filter_by(username=username).first()

        if existing_member_id:
            flash('此手機號碼已被註冊！', 'danger')
        elif existing_username:
            flash('用戶名已被使用！', 'danger')
        else:
            new_user = User(
                member_id=member_id,
                username=username,
                email=email, 
                gender=gender,
                address=address,
                membership_type=membership_type,
                badminton_level=badminton_level,
                is_admin=is_admin
            )
            new_user.set_password(password)
            db.session.add(new_user)
            try:
                db.session.commit()
                flash(f'會員 "{username}" 已成功新增！', 'success')
                return redirect(url_for('query_members')) # 新增後導向查詢頁面
            except Exception as e:
                db.session.rollback()
                flash(f'新增會員失敗: {e}', 'danger')
    
    return render_template(
        'add_user.html',
        gender_options=GENDER_OPTIONS,
        membership_type_options=MEMBERSHIP_TYPE_OPTIONS,
        badminton_level_options=BADMINTON_LEVEL_OPTIONS
    )

@app.route('/admin/edit_user/<int:user_id>', methods=['GET', 'POST'])
def edit_user(user_id):
    """管理員：編輯會員資料頁面"""
    if 'user_id' not in session or not session['is_admin']:
        flash('您沒有權限訪問此頁面。', 'danger')
        return redirect(url_for('index')) # 更改重定向目標為 index

    # 根據內部主鍵 'id' 查詢用戶
    user_to_edit = User.query.get_or_404(user_id)

    if request.method == 'POST':
        user_to_edit.username = request.form['username']
        user_to_edit.email = request.form['email']
        if user_to_edit.email == '':
            user_to_edit.email = None
        user_to_edit.gender = request.form['gender']
        user_to_edit.address = request.form['address']
        user_to_edit.membership_type = request.form['membership_type']
        user_to_edit.badminton_level = int(request.form['badminton_level'])
        user_to_edit.is_admin = True if request.form.get('is_admin') == 'on' else False

        try:
            db.session.commit()
            flash(f'會員 {user_to_edit.username} 的資料已成功更新！', 'success')
            return redirect(url_for('query_members')) # 編輯後導向查詢頁面
        except Exception as e:
            db.session.rollback()
            flash(f'更新會員資料失敗: {e}', 'danger')
            return render_template(
                'edit_user.html',
                user=user_to_edit,
                gender_options=GENDER_OPTIONS,
                membership_type_options=MEMBERSHIP_TYPE_OPTIONS,
                badminton_level_options=BADMINTON_LEVEL_OPTIONS
            )

    return render_template(
        'edit_user.html',
        user=user_to_edit,
        gender_options=GENDER_OPTIONS,
        membership_type_options=MEMBERSHIP_TYPE_OPTIONS,
        badminton_level_options=BADMINTON_LEVEL_OPTIONS
    )

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    """管理員：刪除會員"""
    if 'user_id' not in session or not session['is_admin']:
        flash('您沒有權限執行此操作。', 'danger')
        return redirect(url_for('index'))

    user_to_delete = User.query.get_or_404(user_id)

    # 檢查是否有預約關聯到此會員
    associated_bookings = Booking.query.filter_by(user_id=user_id).first()
    if associated_bookings:
        flash(f'無法刪除會員 "{user_to_delete.username}"，因為有預約資料與其關聯。請先刪除相關預約。', 'danger')
        return redirect(url_for('query_members'))

    # 避免管理員刪除自己
    if user_to_delete.id == session['user_id']:
        flash('您不能刪除自己的管理員帳號。', 'danger')
        return redirect(url_for('query_members'))

    db.session.delete(user_to_delete)
    try:
        db.session.commit()
        flash(f'會員 "{user_to_delete.username}" 已成功刪除！', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'刪除會員失敗: {e}', 'danger')
    
    return redirect(url_for('query_members'))


@app.route('/admin/query_members')
def query_members():
    """管理員：會員資料查詢頁面"""
    if 'user_id' not in session or not session['is_admin']:
        flash('您沒有權限訪問此頁面。', 'danger')
        return redirect(url_for('index')) # 更改重定向目標為 index
    
    members = User.query.all() 
    return render_template('query_members.html', members=members)

@app.route('/admin/export_members_csv')
def export_members_csv():
    """管理員：匯出會員資料為 CSV"""
    if 'user_id' not in session or not session['is_admin']:
        flash('您沒有權限訪問此頁面。', 'danger')
        return redirect(url_for('index')) # 更改重定向目標為 index

    members = User.query.all()

    si = io.StringIO()
    cw = csv.writer(si)

    headers = ['會員手機號碼', '用戶名', '郵箱', '性別', '住家地址', '會員等級', '羽球等級', '是否為管理員']
    cw.writerow(headers)

    for member in members:
        # 匯出時使用 member_id 作為會員手機號碼
        cw.writerow([
            member.formatted_member_id,
            member.username,
            member.email if member.email else '', 
            member.gender,
            member.address,
            member.membership_type,
            member.badminton_level,
            '是' if member.is_admin else '否'
        ])
    
    output = si.getvalue().encode('utf-8-sig') 
    
    response = make_response(output)
    response.headers["Content-Disposition"] = "attachment; filename=members.csv"
    response.headers["Content-type"] = "text/csv; charset=utf-8" 
    return response

@app.route('/query_bookings') # 移除 /admin 前綴，並移除權限檢查
def query_bookings():
    """預約資料查詢頁面 (所有登入用戶可訪問)"""
    if 'user_id' not in session: # 僅檢查是否登入，不檢查是否為管理員
        flash('請先登入才能訪問此頁面。', 'warning')
        return redirect(url_for('login'))
    
    bookings = db.session.query(Booking).join(Court).order_by(
        Booking.booking_date.asc(),
        Court.name.asc(), 
        Booking.start_time.asc()
    ).all()
    
    return render_template('query_bookings.html', bookings=bookings)

@app.route('/admin/export_bookings_csv')
def export_bookings_csv():
    """管理員：匯出預約資料為 CSV"""
    if 'user_id' not in session or not session['is_admin']:
        flash('您沒有權限訪問此頁面。', 'danger')
        return redirect(url_for('index')) # 更改重定向目標為 index

    bookings = db.session.query(Booking).join(Court).order_by(
        Booking.booking_date.asc(),
        Court.name.asc(), 
        Booking.start_time.asc()
    ).all()

    si = io.StringIO()
    cw = csv.writer(si)

    headers = ['預約用戶名', '球場名稱', '預約日期', '開始時間', '結束時間', '時段類別', '狀態', '建檔日期']
    cw.writerow(headers)

    for booking in bookings:
        cw.writerow([
            booking.user.username,
            booking.court.name,
            booking.booking_date.strftime('%Y-%m-%d'), 
            booking.start_time.strftime('%H:%M'), 
            booking.end_time.strftime('%H:%M'), 
            booking.time_slot_category,
            booking.status,
            booking.creation_date.strftime('%Y-%m-%d %H:%M:%S') 
        ])
    
    output = si.getvalue().encode('utf-8-sig') 

    response = make_response(output)
    response.headers["Content-Disposition"] = "attachment; filename=bookings.csv"
    response.headers["Content-type"] = "text/csv; charset=utf-8" 
    return response

@app.route('/cancel_booking/<int:booking_id>', methods=['POST'])
def cancel_booking(booking_id):
    """取消預約功能"""
    if 'user_id' not in session:
        flash('請先登入。', 'warning')
        return redirect(url_for('login'))

    booking = Booking.query.get_or_404(booking_id)

    # 確保只有預約的擁有者或管理員才能取消
    # 這裡使用 session['user_id'] (即用戶的內部主鍵) 進行權限檢查
    if booking.user_id != session['user_id'] and not session.get('is_admin'):
        flash('您沒有權限取消此預約。', 'danger')
        return redirect(url_for('dashboard'))

    # 檢查預約狀態，只有「已預約」的才能取消
    if booking.status == '已預約':
        booking.status = '已取消'
        try:
            db.session.commit()
            flash('預約已成功取消。', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'取消預約失敗: {e}', 'danger')
    else:
        flash('此預約無法取消，因為其狀態不是「已預約」。', 'warning')
    
    return redirect(url_for('dashboard'))

# --- 新增球場管理功能 ---
@app.route('/admin/courts')
def admin_courts():
    """管理員：球場列表頁面 (含新增、修改、刪除入口)"""
    if 'user_id' not in session or not session['is_admin']:
        flash('您沒有權限訪問此頁面。', 'danger')
        return redirect(url_for('index'))
    
    courts = Court.query.all()
    return render_template('admin_courts.html', courts=courts)

@app.route('/admin/add_court', methods=['GET', 'POST'])
def add_court():
    """管理員：新增球場頁面"""
    if 'user_id' not in session or not session['is_admin']:
        flash('您沒有權限訪問此頁面。', 'danger')
        return redirect(url_for('index'))

    if request.method == 'POST':
        name = request.form['name'].strip()
        description = request.form['description'].strip()

        if not name:
            flash('球場名稱不能為空。', 'danger')
            return redirect(url_for('add_court'))

        existing_court = Court.query.filter_by(name=name).first()
        if existing_court:
            flash('球場名稱已存在，請使用其他名稱。', 'danger')
            return redirect(url_for('add_court'))

        new_court = Court(name=name, description=description)
        db.session.add(new_court)
        try:
            db.session.commit()
            flash(f'球場 "{name}" 已成功新增！', 'success')
            return redirect(url_for('admin_courts'))
        except Exception as e:
            db.session.rollback()
            flash(f'新增球場失敗: {e}', 'danger')
            return redirect(url_for('add_court'))

    return render_template('add_court.html')

@app.route('/admin/edit_court/<int:court_id>', methods=['GET', 'POST'])
def edit_court(court_id):
    """管理員：編輯球場頁面"""
    if 'user_id' not in session or not session['is_admin']:
        flash('您沒有權限訪問此頁面。', 'danger')
        return redirect(url_for('index'))

    court_to_edit = Court.query.get_or_404(court_id)

    if request.method == 'POST':
        new_name = request.form['name'].strip()
        new_description = request.form['description'].strip()

        if not new_name:
            flash('球場名稱不能為空。', 'danger')
            return redirect(url_for('edit_court', court_id=court_id))

        # 檢查新名稱是否與其他球場名稱重複 (除了自身)
        existing_court_with_name = Court.query.filter(
            Court.name == new_name, 
            Court.id != court_id
        ).first()

        if existing_court_with_name:
            flash('球場名稱已存在，請使用其他名稱。', 'danger')
            return redirect(url_for('edit_court', court_id=court_id))

        court_to_edit.name = new_name
        court_to_edit.description = new_description
        
        try:
            db.session.commit()
            flash(f'球場 "{new_name}" 已成功更新！', 'success')
            return redirect(url_for('admin_courts'))
        except Exception as e:
            db.session.rollback()
            flash(f'更新球場失敗: {e}', 'danger')
            return redirect(url_for('edit_court', court_id=court_id))

    return render_template('edit_court.html', court=court_to_edit)

@app.route('/admin/delete_court/<int:court_id>', methods=['POST'])
def delete_court(court_id):
    """管理員：刪除球場"""
    if 'user_id' not in session or not session['is_admin']:
        flash('您沒有權限執行此操作。', 'danger')
        return redirect(url_for('index'))

    court_to_delete = Court.query.get_or_404(court_id)

    # 檢查是否有預約關聯到此球場
    associated_bookings = Booking.query.filter_by(court_id=court_id).first()
    if associated_bookings:
        flash(f'無法刪除球場 "{court_to_delete.name}"，因為有預約資料與其關聯。請先刪除相關預約。', 'danger')
        return redirect(url_for('admin_courts'))

    db.session.delete(court_to_delete)
    try:
        db.session.commit()
        flash(f'球場 "{court_to_delete.name}" 已成功刪除！', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'刪除球場失敗: {e}', 'danger')
    
    return redirect(url_for('admin_courts'))

# if __name__ == '__main__':
#     create_tables_and_initial_data() 
#     app.run(debug=True)


if __name__ == '__main__':
    create_tables_and_initial_data() 
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
