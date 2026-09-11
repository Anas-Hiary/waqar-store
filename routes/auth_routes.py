from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('customer_user'):
        return redirect(url_for('auth.profile'))

    error = None
    if request.method == 'POST':
        phone_or_email = request.form.get('login_id', '').strip()
        password = request.form.get('password', '').strip()

        clean_phone = phone_or_email.replace(' ', '').replace('-', '').replace('+962', '0')

        conn = get_db()
        customer = conn.execute('''
            SELECT * FROM customers
            WHERE phone = ? OR phone = ? OR email = ?
        ''', (clean_phone, phone_or_email, phone_or_email)).fetchone()
        conn.close()

        if customer and customer['password_hash'] and check_password_hash(customer['password_hash'], password):
            session['customer_user'] = {
                'id': customer['id'],
                'name': customer['name'],
                'phone': customer['phone'],
                'email': customer['email'],
                'governorate': customer['governorate'],
                'city': customer['city'],
                'address': customer['address']
            }
            session.modified = True
            flash(f"مرحباً بك مجدداً {customer['name']}!", 'success')
            return redirect(url_for('auth.profile'))
        else:
            error = 'بيانات الدخول غير صحيحة، يرجى التأكد من رقم الهاتف وكلمة المرور.'

    return render_template('account/login.html', error=error)

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if session.get('customer_user'):
        return redirect(url_for('auth.profile'))

    error = None
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip() or None
        password = request.form.get('password', '').strip()
        governorate = request.form.get('governorate', '').strip()
        city = request.form.get('city', '').strip()
        address = request.form.get('address', '').strip()

        clean_phone = phone.replace(' ', '').replace('-', '').replace('+962', '0')

        if not name or not clean_phone or not password:
            error = 'يرجى ملء كافة الحقول الأساسية المطلوبة.'
        elif len(password) < 6:
            error = 'يجب أن تكون كلمة المرور من 6 خانات على الأقل.'
        else:
            conn = get_db()
            existing = conn.execute("SELECT id FROM customers WHERE phone = ?", (clean_phone,)).fetchone()
            if existing:
                error = 'رقم الهاتف هذا مسجل مسبقاً، يرجى تسجيل الدخول.'
                conn.close()
            else:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO customers (name, phone, email, password_hash, governorate, city, address)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (name, clean_phone, email, generate_password_hash(password), governorate, city, address))
                cust_id = cursor.lastrowid
                conn.commit()
                conn.close()

                session['customer_user'] = {
                    'id': cust_id,
                    'name': name,
                    'phone': clean_phone,
                    'email': email,
                    'governorate': governorate,
                    'city': city,
                    'address': address
                }
                session.modified = True
                flash('تم إنشاء حسابك بنجاح! أهلاً بك في وَقّار.', 'success')
                return redirect(url_for('auth.profile'))

    conn = get_db()
    zones = conn.execute("SELECT * FROM delivery_zones WHERE is_active = 1").fetchall()
    conn.close()

    return render_template('account/register.html', error=error, zones=zones)

@auth_bp.route('/profile', methods=['GET', 'POST'])
def profile():
    cust = session.get('customer_user')
    if not cust:
        return redirect(url_for('auth.login'))

    conn = get_db()
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip() or None
        governorate = request.form.get('governorate', '').strip()
        city = request.form.get('city', '').strip()
        address = request.form.get('address', '').strip()

        conn.execute('''
            UPDATE customers SET name = ?, email = ?, governorate = ?, city = ?, address = ?
            WHERE id = ?
        ''', (name, email, governorate, city, address, cust['id']))
        conn.commit()

        # Update session
        session['customer_user']['name'] = name
        session['customer_user']['email'] = email
        session['customer_user']['governorate'] = governorate
        session['customer_user']['city'] = city
        session['customer_user']['address'] = address
        session.modified = True

        flash('تم حفظ تعديلات الحساب بنجاح!', 'success')

    # Fetch Customer Orders
    orders = conn.execute('''
        SELECT * FROM orders
        WHERE customer_id = ? OR customer_phone = ?
        ORDER BY id DESC
    ''', (cust['id'], cust['phone'])).fetchall()

    zones = conn.execute("SELECT * FROM delivery_zones WHERE is_active = 1").fetchall()
    conn.close()

    return render_template('account/profile.html', orders=orders, zones=zones)

@auth_bp.route('/logout')
def logout():
    session.pop('customer_user', None)
    flash('تم تسجيل الخروج بنجاح.', 'info')
    return redirect(url_for('store.index'))

