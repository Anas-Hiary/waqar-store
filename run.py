"""
Waqar (وَقّار) Men's Fashion E-Commerce Server Starter
Al-Salt, Jordan
"""
from app import create_app
from seed_data import seed_all

if __name__ == '__main__':
    # Ensure database is seeded with initial data if needed
    seed_all()
    
    app = create_app()
    print("=" * 60)
    print("  متجر وَقّار للملابس الرجالية - السلط، الأردن")
    print("  Waqar Men's Fashion Store is running!")
    print("  الموقع العام (Store): http://127.0.0.1:5000")
    print("  لوحة التحكم (Admin): http://127.0.0.1:5000/admin")
    print("  بيانات الدخول الافتراضية للمدير: admin / admin123")
    print("=" * 60)
    app.run(host='127.0.0.1', port=5000, debug=True)

