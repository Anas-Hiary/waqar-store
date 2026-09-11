import os
from flask import Flask, render_template, session, g
from datetime import datetime
from database import get_db, get_all_settings, init_db
from routes.store_routes import store_bp
from routes.admin_routes import admin_bp
from routes.auth_routes import auth_bp

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'waqar-secret-key-jordan-2026-secure-luxury-fashion')
    
    # Upload folder setup
    upload_folder = os.path.join(app.root_path, 'static', 'uploads')
    os.makedirs(upload_folder, exist_ok=True)
    app.config['UPLOAD_FOLDER'] = upload_folder
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload

    # Ensure DB is initialized
    init_db()

    # Register Blueprints
    app.register_blueprint(store_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(auth_bp, url_prefix='/account')

    # Template context processors
    @app.context_processor
    def inject_global_data():
        settings = get_all_settings()
        
        # Fetch active categories for navigation
        conn = get_db()
        categories = conn.execute(
            "SELECT * FROM categories WHERE is_active = 1 ORDER BY display_order ASC"
        ).fetchall()

        # Calculate session cart count
        cart = session.get('cart', {})
        cart_count = sum(item.get('quantity', 1) for item in cart.values()) if isinstance(cart, dict) else 0

        # Wishlist count
        wishlist = session.get('wishlist', [])
        wishlist_count = len(wishlist) if isinstance(wishlist, list) else 0

        conn.close()

        def format_price(amount):
            if amount is None:
                return ''
            try:
                val = float(amount)
                return f"{val:.2f} د.أ"
            except (ValueError, TypeError):
                return str(amount)

        return {
            'settings': settings,
            'nav_categories': categories,
            'cart_count': cart_count,
            'wishlist_count': wishlist_count,
            'current_admin': session.get('admin_user'),
            'current_customer': session.get('customer_user'),
            'format_price': format_price,
            'current_year': datetime.now().year
        }

    # Custom Error Handlers
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('404.html'), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template('500.html'), 500

    return app

app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
