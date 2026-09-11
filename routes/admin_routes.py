import os
import uuid
from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from database import get_db, get_setting, set_setting, get_all_settings
from cloudinary_service import upload_image, delete_image, is_cloudinary_configured

admin_bp = Blueprint('admin', __name__)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif', 'svg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_user'):
            flash('يرجى تسجيل الدخول للوصول إلى لوحة التحكم.', 'warning')
            return redirect(url_for('admin.login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# =========================================================================
# Authentication
# =========================================================================

@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('admin_user'):
        return redirect(url_for('admin.dashboard'))

    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        conn = get_db()
        admin = conn.execute("SELECT * FROM admins WHERE username = ? OR email = ?", (username, username)).fetchone()
        conn.close()

        if admin and check_password_hash(admin['password_hash'], password):
            session['admin_user'] = {
                'id': admin['id'],
                'username': admin['username'],
                'email': admin['email'],
                'full_name': admin['full_name']
            }
            session.modified = True
            flash(f"أهلاً بك {admin['full_name']} في لوحة تحكم وَقّار!", 'success')
            next_url = request.args.get('next') or url_for('admin.dashboard')
            return redirect(next_url)
        else:
            error = 'اسم المستخدم أو كلمة المرور غير صحيحة.'

    return render_template('admin/login.html', error=error)

@admin_bp.route('/logout')
def logout():
    session.pop('admin_user', None)
    flash('تم تسجيل الخروج بنجاح.', 'info')
    return redirect(url_for('admin.login'))

# =========================================================================
# Dashboard Overview
# =========================================================================

@admin_bp.route('/')
@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    conn = get_db()

    # Metrics
    total_orders = conn.execute("SELECT COUNT(*) as c FROM orders").fetchone()['c']
    new_orders = conn.execute("SELECT COUNT(*) as c FROM orders WHERE status = 'new'").fetchone()['c']
    total_sales = conn.execute("SELECT COALESCE(SUM(total_amount), 0) as s FROM orders WHERE status != 'cancelled'").fetchone()['s']
    
    total_products = conn.execute("SELECT COUNT(*) as c FROM products").fetchone()['c']
    published_products = conn.execute("SELECT COUNT(*) as c FROM products WHERE is_published = 1").fetchone()['c']
    hidden_products = conn.execute("SELECT COUNT(*) as c FROM products WHERE is_published = 0").fetchone()['c']

    # Inventory Metrics
    low_stock = conn.execute('''
        SELECT COUNT(DISTINCT product_id) as c FROM product_variants 
        WHERE stock_quantity > 0 AND stock_quantity <= 3
    ''').fetchone()['c']
    
    out_of_stock = conn.execute('''
        SELECT COUNT(DISTINCT p.id) as c FROM products p
        WHERE (SELECT COALESCE(SUM(stock_quantity), 0) FROM product_variants WHERE product_id = p.id) = 0
    ''').fetchone()['c']

    # Recent Orders
    recent_orders = conn.execute('''
        SELECT * FROM orders ORDER BY id DESC LIMIT 8
    ''').fetchall()

    # Top Selling Products
    top_products = conn.execute('''
        SELECT p.name, p.slug, c.name as category_name,
               (SELECT image_url FROM product_images WHERE product_id = p.id ORDER BY is_primary DESC, sort_order ASC LIMIT 1) as image,
               SUM(oi.quantity) as total_sold, SUM(oi.total_price) as total_revenue
        FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        LEFT JOIN categories c ON p.category_id = c.id
        GROUP BY p.id
        ORDER BY total_sold DESC LIMIT 5
    ''').fetchall()

    # Monthly / Status Distribution for Charts
    status_counts = conn.execute('''
        SELECT status, COUNT(*) as count FROM orders GROUP BY status
    ''').fetchall()
    status_dict = {row['status']: row['count'] for row in status_counts}

    conn.close()

    return render_template(
        'admin/dashboard.html',
        total_orders=total_orders,
        new_orders=new_orders,
        total_sales=total_sales,
        total_products=total_products,
        published_products=published_products,
        hidden_products=hidden_products,
        low_stock=low_stock,
        out_of_stock=out_of_stock,
        recent_orders=recent_orders,
        top_products=top_products,
        status_dict=status_dict
    )

# =========================================================================
# Product Management
# =========================================================================

@admin_bp.route('/products')
@admin_required
def products_list():
    conn = get_db()
    
    q = request.args.get('q', '').strip()
    category_id = request.args.get('category_id', type=int)
    stock_status = request.args.get('stock_status', '').strip()
    status = request.args.get('status', '').strip()

    query = '''
        SELECT p.*, c.name as category_name,
               (SELECT image_url FROM product_images WHERE product_id = p.id ORDER BY is_primary DESC, sort_order ASC LIMIT 1) as primary_image,
               (SELECT COALESCE(SUM(stock_quantity), 0) FROM product_variants WHERE product_id = p.id) as total_stock,
               (SELECT COUNT(*) FROM product_variants WHERE product_id = p.id) as variants_count
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        WHERE 1=1
    '''
    params = []

    if q:
        query += " AND (p.name LIKE ? OR p.sku LIKE ? OR p.description LIKE ?)"
        query_like = f"%{q}%"
        params.extend([query_like, query_like, query_like])

    if category_id:
        query += " AND p.category_id = ?"
        params.append(category_id)

    if status == 'published':
        query += " AND p.is_published = 1"
    elif status == 'hidden':
        query += " AND p.is_published = 0"

    query += " ORDER BY p.id DESC"
    products = conn.execute(query, params).fetchall()

    categories = conn.execute("SELECT * FROM categories ORDER BY display_order ASC").fetchall()
    conn.close()

    # Filter stock status in python if needed
    if stock_status == 'out':
        products = [p for p in products if p['total_stock'] == 0]
    elif stock_status == 'low':
        products = [p for p in products if 0 < p['total_stock'] <= 5]
    elif stock_status == 'in_stock':
        products = [p for p in products if p['total_stock'] > 5]

    return render_template(
        'admin/products/index.html',
        products=products,
        categories=categories,
        search_q=q,
        category_id=category_id,
        stock_status=stock_status,
        status=status
    )

@admin_bp.route('/products/new', methods=['GET', 'POST'])
@admin_required
def product_new():
    conn = get_db()
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        slug = request.form.get('slug', '').strip()
        if not slug:
            slug = name.replace(' ', '-').lower() + f"-{uuid.uuid4().hex[:6]}"
        
        category_id = request.form.get('category_id', type=int)
        description = request.form.get('description', '').strip()
        base_price = float(request.form.get('base_price', 0))
        discount_price_raw = request.form.get('discount_price', '').strip()
        discount_price = float(discount_price_raw) if discount_price_raw else None
        sku = request.form.get('sku', '').strip()
        material = request.form.get('material', '').strip()
        fit = request.form.get('fit', '').strip()
        season = request.form.get('season', '').strip()
        care_instructions = request.form.get('care_instructions', '').strip()
        
        is_featured = 1 if request.form.get('is_featured') else 0
        is_new = 1 if request.form.get('is_new') else 0
        is_bestseller = 1 if request.form.get('is_bestseller') else 0
        is_offer = 1 if request.form.get('is_offer') else 0
        is_published = 1 if request.form.get('is_published') else 0

        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO products (
                category_id, name, slug, description, base_price, discount_price, sku,
                material, fit, season, care_instructions,
                is_featured, is_new, is_bestseller, is_offer, is_published
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            category_id, name, slug, description, base_price, discount_price, sku,
            material, fit, season, care_instructions,
            is_featured, is_new, is_bestseller, is_offer, is_published
        ))
        product_id = cursor.lastrowid

        # 1. Handle Uploaded Images (Cloudinary or local fallback)
        files = request.files.getlist('images')
        for idx, file in enumerate(files):
            if file and allowed_file(file.filename):
                image_url = upload_image(file, folder="waqar_store/products", prefix=f"prod_{product_id}")
                if image_url:
                    cursor.execute('''
                        INSERT INTO product_images (product_id, image_url, is_primary, sort_order)
                        VALUES (?, ?, ?, ?)
                    ''', (product_id, image_url, 1 if idx == 0 else 0, idx))

        # Handle direct image URLs if provided
        image_urls_raw = request.form.get('image_urls', '').strip()
        if image_urls_raw:
            for idx, line in enumerate(image_urls_raw.splitlines()):
                url_clean = line.strip()
                if url_clean:
                    cursor.execute('''
                        INSERT INTO product_images (product_id, image_url, is_primary, sort_order)
                        VALUES (?, ?, ?, ?)
                    ''', (product_id, url_clean, 1 if idx == 0 and not files else 0, idx + 10))

        # 2. Handle Color x Size Variants Matrix
        # Expecting variant rows from form arrays: variant_color[], variant_hex[], variant_size[], variant_stock[]
        colors = request.form.getlist('variant_color[]')
        hexes = request.form.getlist('variant_hex[]')
        sizes = request.form.getlist('variant_size[]')
        stocks = request.form.getlist('variant_stock[]')

        for i in range(len(colors)):
            c_name = colors[i].strip()
            c_hex = hexes[i].strip() if i < len(hexes) else '#111111'
            s_name = sizes[i].strip() if i < len(sizes) else 'M'
            s_qty = int(stocks[i]) if i < len(stocks) and stocks[i].isdigit() else 0

            if c_name and s_name:
                cursor.execute('''
                    INSERT INTO product_variants (product_id, color_name, color_hex, size_name, stock_quantity, sku_variant)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (product_id, c_name, c_hex, s_name, s_qty, f"{sku}-{s_name}"))

        conn.commit()
        conn.close()
        flash('تمت إضافة المنتج بنجاح!', 'success')
        return redirect(url_for('admin.products_list'))

    categories = conn.execute("SELECT * FROM categories ORDER BY display_order ASC").fetchall()
    conn.close()
    return render_template('admin/products/form.html', product=None, categories=categories, images=[], variants=[])

@admin_bp.route('/products/edit/<int:product_id>', methods=['GET', 'POST'])
@admin_required
def product_edit(product_id):
    conn = get_db()
    product = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if not product:
        conn.close()
        flash('المنتج غير موجود.', 'danger')
        return redirect(url_for('admin.products_list'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        slug = request.form.get('slug', '').strip() or product['slug']
        category_id = request.form.get('category_id', type=int)
        description = request.form.get('description', '').strip()
        base_price = float(request.form.get('base_price', 0))
        discount_price_raw = request.form.get('discount_price', '').strip()
        discount_price = float(discount_price_raw) if discount_price_raw else None
        sku = request.form.get('sku', '').strip()
        material = request.form.get('material', '').strip()
        fit = request.form.get('fit', '').strip()
        season = request.form.get('season', '').strip()
        care_instructions = request.form.get('care_instructions', '').strip()
        
        is_featured = 1 if request.form.get('is_featured') else 0
        is_new = 1 if request.form.get('is_new') else 0
        is_bestseller = 1 if request.form.get('is_bestseller') else 0
        is_offer = 1 if request.form.get('is_offer') else 0
        is_published = 1 if request.form.get('is_published') else 0

        cursor = conn.cursor()
        cursor.execute('''
            UPDATE products SET
                category_id = ?, name = ?, slug = ?, description = ?, base_price = ?,
                discount_price = ?, sku = ?, material = ?, fit = ?, season = ?,
                care_instructions = ?, is_featured = ?, is_new = ?, is_bestseller = ?,
                is_offer = ?, is_published = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (
            category_id, name, slug, description, base_price, discount_price, sku,
            material, fit, season, care_instructions,
            is_featured, is_new, is_bestseller, is_offer, is_published, product_id
        ))

        # 1. Handle New Uploaded Images (Cloudinary or local fallback)
        files = request.files.getlist('images')
        for idx, file in enumerate(files):
            if file and allowed_file(file.filename):
                image_url = upload_image(file, folder="waqar_store/products", prefix=f"prod_{product_id}")
                if image_url:
                    cursor.execute('''
                        INSERT INTO product_images (product_id, image_url, is_primary, sort_order)
                        VALUES (?, ?, 0, 100)
                    ''', (product_id, image_url))

        # Handle direct image URLs if added
        image_urls_raw = request.form.get('image_urls', '').strip()
        if image_urls_raw:
            for idx, line in enumerate(image_urls_raw.splitlines()):
                url_clean = line.strip()
                if url_clean:
                    cursor.execute('''
                        INSERT INTO product_images (product_id, image_url, is_primary, sort_order)
                        VALUES (?, ?, 0, 100)
                    ''', (product_id, url_clean))

        # Primary Image update
        primary_img_id = request.form.get('primary_image_id', type=int)
        if primary_img_id:
            cursor.execute("UPDATE product_images SET is_primary = 0 WHERE product_id = ?", (product_id,))
            cursor.execute("UPDATE product_images SET is_primary = 1 WHERE id = ? AND product_id = ?", (primary_img_id, product_id))

        # Delete selected images (removes from Cloudinary/storage if applicable)
        delete_image_ids = request.form.getlist('delete_images[]')
        for img_id in delete_image_ids:
            img_row = cursor.execute("SELECT image_url FROM product_images WHERE id = ? AND product_id = ?", (img_id, product_id)).fetchone()
            if img_row:
                delete_image(img_row['image_url'])
            cursor.execute("DELETE FROM product_images WHERE id = ? AND product_id = ?", (img_id, product_id))

        # 2. Handle Color x Size Variants Matrix
        cursor.execute("DELETE FROM product_variants WHERE product_id = ?", (product_id,))
        colors = request.form.getlist('variant_color[]')
        hexes = request.form.getlist('variant_hex[]')
        sizes = request.form.getlist('variant_size[]')
        stocks = request.form.getlist('variant_stock[]')

        for i in range(len(colors)):
            c_name = colors[i].strip()
            c_hex = hexes[i].strip() if i < len(hexes) else '#111111'
            s_name = sizes[i].strip() if i < len(sizes) else 'M'
            s_qty = int(stocks[i]) if i < len(stocks) and stocks[i].isdigit() else 0

            if c_name and s_name:
                cursor.execute('''
                    INSERT INTO product_variants (product_id, color_name, color_hex, size_name, stock_quantity, sku_variant)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (product_id, c_name, c_hex, s_name, s_qty, f"{sku}-{s_name}"))

        conn.commit()
        conn.close()
        flash('تم تحديث بيانات المنتج والمخزون بنجاح!', 'success')
        return redirect(url_for('admin.products_list'))

    categories = conn.execute("SELECT * FROM categories ORDER BY display_order ASC").fetchall()
    images = conn.execute("SELECT * FROM product_images WHERE product_id = ? ORDER BY is_primary DESC, sort_order ASC", (product_id,)).fetchall()
    variants = conn.execute("SELECT * FROM product_variants WHERE product_id = ? ORDER BY id ASC", (product_id,)).fetchall()
    conn.close()

    return render_template(
        'admin/products/form.html',
        product=product,
        categories=categories,
        images=images,
        variants=variants
    )

@admin_bp.route('/products/delete/<int:product_id>', methods=['POST'])
@admin_required
def product_delete(product_id):
    conn = get_db()
    # Clean up images from Cloudinary or local storage
    img_rows = conn.execute("SELECT image_url FROM product_images WHERE product_id = ?", (product_id,)).fetchall()
    for r in img_rows:
        delete_image(r['image_url'])

    conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()
    flash('تم حذف المنتج بنجاح.', 'info')
    return redirect(url_for('admin.products_list'))

@admin_bp.route('/products/duplicate/<int:product_id>', methods=['POST'])
@admin_required
def product_duplicate(product_id):
    conn = get_db()
    prod = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if prod:
        new_name = f"{prod['name']} (نسخة)"
        new_slug = f"{prod['slug']}-copy-{uuid.uuid4().hex[:4]}"
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO products (
                category_id, name, slug, description, base_price, discount_price, sku,
                material, fit, season, care_instructions,
                is_featured, is_new, is_bestseller, is_offer, is_published
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        ''', (
            prod['category_id'], new_name, new_slug, prod['description'], prod['base_price'],
            prod['discount_price'], f"{prod['sku']}-COPY", prod['material'], prod['fit'],
            prod['season'], prod['care_instructions'], prod['is_featured'], prod['is_new'],
            prod['is_bestseller'], prod['is_offer']
        ))
        new_id = cursor.lastrowid

        # Copy images
        images = conn.execute("SELECT * FROM product_images WHERE product_id = ?", (product_id,)).fetchall()
        for img in images:
            cursor.execute('''
                INSERT INTO product_images (product_id, image_url, is_primary, sort_order)
                VALUES (?, ?, ?, ?)
            ''', (new_id, img['image_url'], img['is_primary'], img['sort_order']))

        # Copy variants
        variants = conn.execute("SELECT * FROM product_variants WHERE product_id = ?", (product_id,)).fetchall()
        for v in variants:
            cursor.execute('''
                INSERT INTO product_variants (product_id, color_name, color_hex, size_name, stock_quantity, sku_variant)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (new_id, v['color_name'], v['color_hex'], v['size_name'], v['stock_quantity'], v['sku_variant']))

        conn.commit()
        flash('تم تكرار المنتج بنجاح، يمكنك الآن تعديله.', 'success')

    conn.close()
    return redirect(url_for('admin.products_list'))

@admin_bp.route('/products/toggle-publish/<int:product_id>', methods=['POST'])
@admin_required
def product_toggle_publish(product_id):
    conn = get_db()
    conn.execute("UPDATE products SET is_published = 1 - is_published WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# =========================================================================
# Inventory Management
# =========================================================================

@admin_bp.route('/inventory')
@admin_required
def inventory_list():
    conn = get_db()
    q = request.args.get('q', '').strip()
    status_filter = request.args.get('status', '').strip()

    query = '''
        SELECT pv.*, p.name as product_name, p.slug as product_slug, p.sku as product_sku,
               c.name as category_name,
               (SELECT image_url FROM product_images WHERE product_id = p.id ORDER BY is_primary DESC, sort_order ASC LIMIT 1) as primary_image
        FROM product_variants pv
        JOIN products p ON pv.product_id = p.id
        LEFT JOIN categories c ON p.category_id = c.id
        WHERE 1=1
    '''
    params = []

    if q:
        query += " AND (p.name LIKE ? OR pv.color_name LIKE ? OR pv.size_name LIKE ? OR pv.sku_variant LIKE ?)"
        ql = f"%{q}%"
        params.extend([ql, ql, ql, ql])

    if status_filter == 'out':
        query += " AND pv.stock_quantity = 0"
    elif status_filter == 'low':
        query += " AND pv.stock_quantity > 0 AND pv.stock_quantity <= 3"
    elif status_filter == 'available':
        query += " AND pv.stock_quantity > 3"

    query += " ORDER BY pv.stock_quantity ASC, p.id DESC"
    variants = conn.execute(query, params).fetchall()
    conn.close()

    return render_template('admin/inventory/index.html', variants=variants, search_q=q, status_filter=status_filter)

@admin_bp.route('/inventory/update-stock', methods=['POST'])
@admin_required
def inventory_update_stock():
    data = request.get_json() or {}
    variant_id = data.get('variant_id')
    new_stock = data.get('stock')

    if variant_id is None or new_stock is None:
        return jsonify({'success': False, 'message': 'بيانات غير مكتملة.'}), 400

    conn = get_db()
    conn.execute("UPDATE product_variants SET stock_quantity = ? WHERE id = ?", (max(0, int(new_stock)), variant_id))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'تم تحديث المخزون بنجاح.'})

# =========================================================================
# Category Management
# =========================================================================

@admin_bp.route('/categories', methods=['GET', 'POST'])
@admin_required
def categories_list():
    conn = get_db()
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        slug = request.form.get('slug', '').strip() or name.replace(' ', '-').lower()
        description = request.form.get('description', '').strip()
        image_url = request.form.get('image_url', '').strip()
        display_order = int(request.form.get('display_order', 0))

        # Handle image file upload if present (Cloudinary or local fallback)
        file = request.files.get('image_file')
        if file and allowed_file(file.filename):
            uploaded = upload_image(file, folder="waqar_store/categories", prefix="cat")
            if uploaded:
                image_url = uploaded

        conn.execute('''
            INSERT INTO categories (name, slug, description, image_url, display_order, is_active)
            VALUES (?, ?, ?, ?, ?, 1)
        ''', (name, slug, description, image_url, display_order))
        conn.commit()
        flash('تمت إضافة التصنيف بنجاح!', 'success')
        return redirect(url_for('admin.categories_list'))

    categories = conn.execute('''
        SELECT c.*, (SELECT COUNT(*) FROM products WHERE category_id = c.id) as products_count
        FROM categories c
        ORDER BY display_order ASC, id ASC
    ''').fetchall()
    conn.close()

    return render_template('admin/categories/index.html', categories=categories)

@admin_bp.route('/categories/edit/<int:category_id>', methods=['POST'])
@admin_required
def category_edit(category_id):
    conn = get_db()
    name = request.form.get('name', '').strip()
    slug = request.form.get('slug', '').strip()
    description = request.form.get('description', '').strip()
    image_url = request.form.get('image_url', '').strip()
    display_order = int(request.form.get('display_order', 0))
    is_active = 1 if request.form.get('is_active') else 0

    file = request.files.get('image_file')
    if file and allowed_file(file.filename):
        uploaded = upload_image(file, folder="waqar_store/categories", prefix="cat")
        if uploaded:
            image_url = uploaded

    conn.execute('''
        UPDATE categories SET
            name = ?, slug = ?, description = ?, image_url = COALESCE(NULLIF(?, ''), image_url),
            display_order = ?, is_active = ?
        WHERE id = ?
    ''', (name, slug, description, image_url, display_order, is_active, category_id))
    conn.commit()
    conn.close()
    flash('تم تحديث التصنيف بنجاح!', 'success')
    return redirect(url_for('admin.categories_list'))

@admin_bp.route('/categories/delete/<int:category_id>', methods=['POST'])
@admin_required
def category_delete(category_id):
    conn = get_db()
    cat = conn.execute("SELECT image_url FROM categories WHERE id = ?", (category_id,)).fetchone()
    if cat and cat['image_url']:
        delete_image(cat['image_url'])

    conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
    conn.commit()
    conn.close()
    flash('تم حذف التصنيف بنجاح.', 'info')
    return redirect(url_for('admin.categories_list'))

# =========================================================================
# Order Management
# =========================================================================

@admin_bp.route('/orders')
@admin_required
def orders_list():
    conn = get_db()
    status = request.args.get('status', '').strip()
    q = request.args.get('q', '').strip()
    date_from = request.args.get('date_from', '').strip()

    query = "SELECT * FROM orders WHERE 1=1"
    params = []

    if status:
        query += " AND status = ?"
        params.append(status)

    if q:
        query += " AND (order_number LIKE ? OR customer_name LIKE ? OR customer_phone LIKE ?)"
        ql = f"%{q}%"
        params.extend([ql, ql, ql])

    if date_from:
        query += " AND DATE(created_at) >= DATE(?)"
        params.append(date_from)

    query += " ORDER BY id DESC"
    orders = conn.execute(query, params).fetchall()

    # Status summary counts
    status_counts = conn.execute("SELECT status, COUNT(*) as c FROM orders GROUP BY status").fetchall()
    counts_map = {r['status']: r['c'] for r in status_counts}

    conn.close()

    return render_template(
        'admin/orders/index.html',
        orders=orders,
        status_filter=status,
        search_q=q,
        counts_map=counts_map
    )

@admin_bp.route('/orders/<int:order_id>')
@admin_required
def order_detail(order_id):
    conn = get_db()
    order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        conn.close()
        flash('الطلب غير موجود.', 'danger')
        return redirect(url_for('admin.orders_list'))

    items = conn.execute("SELECT * FROM order_items WHERE order_id = ?", (order_id,)).fetchall()
    conn.close()

    return render_template('admin/orders/detail.html', order=order, items=items)

@admin_bp.route('/orders/<int:order_id>/status', methods=['POST'])
@admin_required
def order_update_status(order_id):
    new_status = request.form.get('status', '').strip()
    valid_statuses = ['new', 'processing', 'shipped', 'delivered', 'cancelled']

    if new_status in valid_statuses:
        conn = get_db()
        conn.execute("UPDATE orders SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_status, order_id))
        conn.commit()
        conn.close()
        flash('تم تغيير حالة الطلب بنجاح!', 'success')

    return redirect(url_for('admin.order_detail', order_id=order_id))

@admin_bp.route('/orders/<int:order_id>/invoice')
@admin_required
def order_invoice(order_id):
    conn = get_db()
    order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    items = conn.execute("SELECT * FROM order_items WHERE order_id = ?", (order_id,)).fetchall()
    settings = get_all_settings()
    conn.close()

    return render_template('admin/orders/invoice.html', order=order, items=items, settings=settings)

# =========================================================================
# Customer Management
# =========================================================================

@admin_bp.route('/customers')
@admin_required
def customers_list():
    conn = get_db()
    q = request.args.get('q', '').strip()

    query = '''
        SELECT c.*,
               COUNT(o.id) as orders_count,
               COALESCE(SUM(o.total_amount), 0) as total_spent,
               MAX(o.created_at) as last_order_date
        FROM customers c
        LEFT JOIN orders o ON o.customer_id = c.id
        WHERE 1=1
    '''
    params = []

    if q:
        query += " AND (c.name LIKE ? OR c.phone LIKE ? OR c.city LIKE ?)"
        ql = f"%{q}%"
        params.extend([ql, ql, ql])

    query += " GROUP BY c.id ORDER BY total_spent DESC, c.id DESC"
    customers = conn.execute(query, params).fetchall()
    conn.close()

    return render_template('admin/customers/index.html', customers=customers, search_q=q)

# =========================================================================
# Delivery Zones Management
# =========================================================================

@admin_bp.route('/delivery-zones', methods=['GET', 'POST'])
@admin_required
def delivery_zones_list():
    conn = get_db()
    if request.method == 'POST':
        name = request.form.get('governorate_name', '').strip()
        fee = float(request.form.get('fee', 2.0))
        estimated_time = request.form.get('estimated_time', '24 - 48 ساعة').strip()

        conn.execute('''
            INSERT INTO delivery_zones (governorate_name, fee, estimated_time, is_active)
            VALUES (?, ?, ?, 1)
        ''', (name, fee, estimated_time))
        conn.commit()
        flash('تمت إضافة منطقة التوصيل بنجاح!', 'success')
        return redirect(url_for('admin.delivery_zones_list'))

    zones = conn.execute("SELECT * FROM delivery_zones ORDER BY id ASC").fetchall()
    conn.close()

    return render_template('admin/delivery/index.html', zones=zones)

@admin_bp.route('/delivery-zones/edit/<int:zone_id>', methods=['POST'])
@admin_required
def delivery_zone_edit(zone_id):
    conn = get_db()
    name = request.form.get('governorate_name', '').strip()
    fee = float(request.form.get('fee', 2.0))
    estimated_time = request.form.get('estimated_time', '').strip()
    is_active = 1 if request.form.get('is_active') else 0

    conn.execute('''
        UPDATE delivery_zones SET
            governorate_name = ?, fee = ?, estimated_time = ?, is_active = ?
        WHERE id = ?
    ''', (name, fee, estimated_time, is_active, zone_id))
    conn.commit()
    conn.close()
    flash('تم تحديث بيانات التوصيل بنجاح!', 'success')
    return redirect(url_for('admin.delivery_zones_list'))

@admin_bp.route('/delivery-zones/delete/<int:zone_id>', methods=['POST'])
@admin_required
def delivery_zone_delete(zone_id):
    conn = get_db()
    conn.execute("DELETE FROM delivery_zones WHERE id = ?", (zone_id,))
    conn.commit()
    conn.close()
    flash('تم حذف منطقة التوصيل.', 'info')
    return redirect(url_for('admin.delivery_zones_list'))

# =========================================================================
# Coupons Management
# =========================================================================

@admin_bp.route('/coupons', methods=['GET', 'POST'])
@admin_required
def coupons_list():
    conn = get_db()
    if request.method == 'POST':
        code = request.form.get('code', '').strip().upper()
        discount_type = request.form.get('discount_type', 'percent')
        discount_value = float(request.form.get('discount_value', 10))
        min_order_amount = float(request.form.get('min_order_amount', 0))
        max_uses = int(request.form.get('max_uses', 100)) if request.form.get('max_uses') else None
        expires_at = request.form.get('expires_at') or None

        conn.execute('''
            INSERT INTO coupons (code, discount_type, discount_value, min_order_amount, max_uses, expires_at, is_active)
            VALUES (?, ?, ?, ?, ?, ?, 1)
        ''', (code, discount_type, discount_value, min_order_amount, max_uses, expires_at))
        conn.commit()
        flash('تم إنشاء الكوبون بنجاح!', 'success')
        return redirect(url_for('admin.coupons_list'))

    coupons = conn.execute("SELECT * FROM coupons ORDER BY id DESC").fetchall()
    conn.close()

    return render_template('admin/coupons/index.html', coupons=coupons)

@admin_bp.route('/coupons/delete/<int:coupon_id>', methods=['POST'])
@admin_required
def coupon_delete(coupon_id):
    conn = get_db()
    conn.execute("DELETE FROM coupons WHERE id = ?", (coupon_id,))
    conn.commit()
    conn.close()
    flash('تم حذف الكوبون بنجاح.', 'info')
    return redirect(url_for('admin.coupons_list'))

# =========================================================================
# Reviews Moderation
# =========================================================================

@admin_bp.route('/reviews')
@admin_required
def reviews_list():
    conn = get_db()
    reviews = conn.execute('''
        SELECT pr.*, p.name as product_name, p.slug as product_slug,
               (SELECT image_url FROM product_images WHERE product_id = p.id ORDER BY is_primary DESC, sort_order ASC LIMIT 1) as product_image
        FROM product_reviews pr
        JOIN products p ON pr.product_id = p.id
        ORDER BY pr.id DESC
    ''').fetchall()
    conn.close()

    return render_template('admin/reviews/index.html', reviews=reviews)

@admin_bp.route('/reviews/<int:review_id>/approve', methods=['POST'])
@admin_required
def review_approve(review_id):
    conn = get_db()
    conn.execute("UPDATE product_reviews SET is_approved = 1 WHERE id = ?", (review_id,))
    conn.commit()
    conn.close()
    flash('تمت الموافقة على التقييم ونشره في الموقع.', 'success')
    return redirect(url_for('admin.reviews_list'))

@admin_bp.route('/reviews/<int:review_id>/reject', methods=['POST'])
@admin_required
def review_reject(review_id):
    conn = get_db()
    conn.execute("UPDATE product_reviews SET is_approved = 0 WHERE id = ?", (review_id,))
    conn.commit()
    conn.close()
    flash('تم إخفاء التقييم.', 'info')
    return redirect(url_for('admin.reviews_list'))

@admin_bp.route('/reviews/<int:review_id>/delete', methods=['POST'])
@admin_required
def review_delete(review_id):
    conn = get_db()
    conn.execute("DELETE FROM product_reviews WHERE id = ?", (review_id,))
    conn.commit()
    conn.close()
    flash('تم حذف التقييم نهائياً.', 'info')
    return redirect(url_for('admin.reviews_list'))

# =========================================================================
# Homepage Content Editor
# =========================================================================

@admin_bp.route('/homepage', methods=['GET', 'POST'])
@admin_required
def homepage_editor():
    if request.method == 'POST':
        keys = [
            'hero_title', 'hero_subtitle', 'hero_btn1_text', 'hero_btn1_url',
            'hero_btn2_text', 'hero_btn2_url', 'hero_image', 'announcement_bar',
            'why_waqar_1_title', 'why_waqar_1_desc',
            'why_waqar_2_title', 'why_waqar_2_desc',
            'why_waqar_3_title', 'why_waqar_3_desc',
            'why_waqar_4_title', 'why_waqar_4_desc'
        ]
        
        # Handle hero image file upload (Cloudinary or local fallback)
        file = request.files.get('hero_image_file')
        if file and allowed_file(file.filename):
            uploaded = upload_image(file, folder="waqar_store/homepage", prefix="hero")
            if uploaded:
                set_setting('hero_image', uploaded)

        for k in keys:
            if k in request.form and request.form[k]:
                set_setting(k, request.form[k].strip())

        flash('تم حفظ تعديلات الصفحة الرئيسية بنجاح!', 'success')
        return redirect(url_for('admin.homepage_editor'))

    settings = get_all_settings()
    return render_template('admin/homepage_editor.html', settings=settings)

# =========================================================================
# Store Settings & Admin Profile
# =========================================================================

@admin_bp.route('/settings', methods=['GET', 'POST'])
@admin_required
def settings():
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'update_settings':
            keys = [
                'store_name', 'store_business', 'tagline', 'city', 'country',
                'phone', 'whatsapp', 'instagram', 'instagram_url', 'store_address',
                'google_maps_embed', 'working_hours', 'free_delivery_threshold',
                'exchange_policy', 'privacy_policy', 'terms_conditions'
            ]
            for k in keys:
                if k in request.form:
                    set_setting(k, request.form[k].strip())

            flash('تم حفظ إعدادات المتجر بنجاح!', 'success')

        elif action == 'change_password':
            old_pass = request.form.get('old_password', '')
            new_pass = request.form.get('new_password', '')
            confirm_pass = request.form.get('confirm_password', '')

            conn = get_db()
            admin = conn.execute("SELECT * FROM admins WHERE id = ?", (session['admin_user']['id'],)).fetchone()

            if not admin or not check_password_hash(admin['password_hash'], old_pass):
                flash('كلمة المرور الحالية غير صحيحة.', 'danger')
            elif len(new_pass) < 6:
                flash('يجب أن تتكون كلمة المرور الجديدة من 6 خانات على الأقل.', 'danger')
            elif new_pass != confirm_pass:
                flash('كلمة المرور الجديدة وتأكيدها غير متطابقين.', 'danger')
            else:
                new_hash = generate_password_hash(new_pass)
                conn.execute("UPDATE admins SET password_hash = ? WHERE id = ?", (new_hash, admin['id']))
                conn.commit()
                flash('تم تغيير كلمة المرور بنجاح!', 'success')

            conn.close()

        return redirect(url_for('admin.settings'))

    settings = get_all_settings()
    return render_template('admin/settings.html', settings=settings)

