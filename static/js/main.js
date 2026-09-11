/**
 * WAQAR Men's Fashion - Main Client-side Interactivity
 */

// Toast Notifications System
function showToast(message, type = 'success') {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  toast.className = 'waqar-toast';
  
  let icon = '<i class="fas fa-check-circle text-amber-400"></i>';
  if (type === 'error' || type === 'danger') {
    icon = '<i class="fas fa-exclamation-circle text-red-400"></i>';
    toast.style.borderColor = '#ef4444';
  } else if (type === 'warning') {
    icon = '<i class="fas fa-exclamation-triangle text-amber-300"></i>';
    toast.style.borderColor = '#f59e0b';
  }

  toast.innerHTML = `
    <span class="text-xl">${icon}</span>
    <span class="flex-1 font-medium text-sm text-zinc-100">${message}</span>
  `;

  container.appendChild(toast);

  setTimeout(() => {
    toast.classList.add('hide');
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// Cart Drawer Functions
function openCartDrawer() {
  const drawer = document.getElementById('cart-drawer');
  const backdrop = document.getElementById('cart-backdrop');
  if (drawer && backdrop) {
    drawer.classList.add('active');
    backdrop.classList.add('active');
    document.body.style.overflow = 'hidden';
  }
}

function closeCartDrawer() {
  const drawer = document.getElementById('cart-drawer');
  const backdrop = document.getElementById('cart-backdrop');
  if (drawer && backdrop) {
    drawer.classList.remove('active');
    backdrop.classList.remove('active');
    document.body.style.overflow = '';
  }
}

// Mobile Menu Functions
function openMobileMenu() {
  const menu = document.getElementById('mobile-menu-drawer');
  const backdrop = document.getElementById('menu-backdrop');
  if (menu && backdrop) {
    menu.classList.add('active');
    backdrop.classList.add('active');
    document.body.style.overflow = 'hidden';
  }
}

function closeMobileMenu() {
  const menu = document.getElementById('mobile-menu-drawer');
  const backdrop = document.getElementById('menu-backdrop');
  if (menu && backdrop) {
    menu.classList.remove('active');
    backdrop.classList.remove('active');
    document.body.style.overflow = '';
  }
}

// Search Modal
function openSearchModal() {
  const modal = document.getElementById('search-modal');
  if (modal) {
    modal.classList.remove('hidden');
    const input = document.getElementById('search-modal-input');
    if (input) {
      setTimeout(() => input.focus(), 100);
    }
  }
}

function closeSearchModal() {
  const modal = document.getElementById('search-modal');
  if (modal) modal.classList.add('hidden');
}

// Wishlist Toggle
async function toggleWishlist(productId, btnElement) {
  try {
    const res = await fetch('/api/wishlist/toggle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ product_id: productId })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, 'success');
      
      // Update counters
      document.querySelectorAll('.wishlist-counter').forEach(el => {
        el.textContent = data.wishlist_count;
        el.style.display = data.wishlist_count > 0 ? 'inline-flex' : 'none';
      });

      // Update heart icon styling
      if (btnElement) {
        const heart = btnElement.querySelector('i');
        if (heart) {
          if (data.action === 'added') {
            heart.classList.remove('far');
            heart.classList.add('fas', 'text-amber-400');
          } else {
            heart.classList.remove('fas', 'text-amber-400');
            heart.classList.add('far');
          }
        }
      }
    } else {
      showToast(data.message, 'error');
    }
  } catch (err) {
    showToast('حدث خطأ أثناء تحديث المفضلة.', 'error');
  }
}

// Live Search with Debounce
let searchTimeout = null;
function handleSearchInput(query) {
  clearTimeout(searchTimeout);
  const container = document.getElementById('search-suggestions-container');
  if (!container) return;

  if (query.trim().length < 2) {
    container.innerHTML = '';
    container.classList.add('hidden');
    return;
  }

  searchTimeout = setTimeout(async () => {
    try {
      const res = await fetch(`/api/search/suggestions?q=${encodeURIComponent(query)}`);
      const data = await res.json();
      
      if (data.results && data.results.length > 0) {
        container.innerHTML = data.results.map(item => `
          <a href="/product/${item.slug}" class="flex items-center gap-3 p-3 hover:bg-zinc-800 transition rounded-lg border-b border-zinc-800 last:border-0">
            <img src="${item.image}" alt="${item.name}" class="w-12 h-14 object-cover rounded bg-zinc-900">
            <div class="flex-1 text-right">
              <h4 class="text-sm font-semibold text-zinc-100">${item.name}</h4>
              <span class="text-xs text-zinc-400">${item.category || 'ملابس رجالية'}</span>
            </div>
            <span class="text-sm font-bold text-amber-400">${parseFloat(item.price).toFixed(2)} د.أ</span>
          </a>
        `).join('');
        container.classList.remove('hidden');
      } else {
        container.innerHTML = `<div class="p-4 text-center text-sm text-zinc-400">لا توجد نتائج مطابقة لبحثك</div>`;
        container.classList.remove('hidden');
      }
    } catch (err) {
      console.error(err);
    }
  }, 250);
}

// Add to Cart
async function addToCart(productId, color, size, quantity = 1, openDrawer = true) {
  if (!color || !size) {
    showToast('يرجى اختيار اللون والمقاس أولاً.', 'warning');
    return false;
  }

  try {
    const res = await fetch('/api/cart/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ product_id: productId, color, size, quantity })
    });
    const data = await res.json();

    if (data.success) {
      showToast(data.message, 'success');
      // Update cart counters
      document.querySelectorAll('.cart-counter').forEach(el => {
        el.textContent = data.cart_count;
        el.style.display = data.cart_count > 0 ? 'inline-flex' : 'none';
      });

      if (openDrawer) {
        // Refresh page or open drawer
        setTimeout(() => {
          window.location.href = '/cart';
        }, 600);
      }
      return true;
    } else {
      showToast(data.message, 'error');
      return false;
    }
  } catch (err) {
    showToast('حدث خطأ أثناء إضافة المنتج إلى السلة.', 'error');
    return false;
  }
}

// Update Cart Item Quantity
async function updateCartItem(key, quantity) {
  try {
    const res = await fetch('/api/cart/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key, quantity })
    });
    const data = await res.json();
    if (data.success) {
      window.location.reload();
    } else {
      showToast(data.message, 'error');
    }
  } catch (err) {
    showToast('تعذر تحديث السلة.', 'error');
  }
}

// Remove Cart Item
async function removeCartItem(key) {
  try {
    const res = await fetch('/api/cart/remove', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, 'info');
      setTimeout(() => window.location.reload(), 400);
    } else {
      showToast(data.message, 'error');
    }
  } catch (err) {
    showToast('تعذر حذف العنصر.', 'error');
  }
}

// Apply Coupon
async function applyCoupon() {
  const input = document.getElementById('coupon-input');
  if (!input || !input.value.trim()) {
    showToast('يرجى إدخال رمز الكوبون.', 'warning');
    return;
  }

  try {
    const res = await fetch('/api/coupon/apply', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: input.value.trim() })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, 'success');
      setTimeout(() => window.location.reload(), 500);
    } else {
      showToast(data.message, 'error');
    }
  } catch (err) {
    showToast('تعذر تطبيق الكوبون.', 'error');
  }
}

// Remove Coupon
async function removeCoupon() {
  try {
    const res = await fetch('/api/coupon/remove', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, 'info');
      setTimeout(() => window.location.reload(), 500);
    }
  } catch (err) {
    showToast('تعذر إزالة الكوبون.', 'error');
  }
}

// DOM Init
document.addEventListener('DOMContentLoaded', () => {
  // ESC key closes modals
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeSearchModal();
      closeCartDrawer();
      closeMobileMenu();
    }
  });
});

