/**
 * WAQAR Admin Dashboard Scripts
 */

// Dynamic Variant Matrix Builder
function addVariantRow(color = 'أسود', hex = '#111111', size = 'M', stock = 5) {
  const container = document.getElementById('variant-rows-container');
  if (!container) return;

  const row = document.createElement('tr');
  row.className = 'border-b border-zinc-800 hover:bg-zinc-800/40 transition';
  row.innerHTML = `
    <td class="p-3">
      <div class="flex items-center gap-2">
        <input type="color" name="variant_hex[]" value="${hex}" class="w-8 h-8 rounded border-0 bg-transparent cursor-pointer" onchange="this.nextElementSibling.style.backgroundColor = this.value">
        <input type="text" name="variant_color[]" value="${color}" placeholder="اسم اللون (مثال: أسود)" class="bg-zinc-900 border border-zinc-700 rounded px-3 py-1.5 text-sm text-zinc-100 focus:outline-none focus:border-amber-400 flex-1" required>
      </div>
    </td>
    <td class="p-3">
      <input type="text" name="variant_size[]" value="${size}" placeholder="المقاس (مثال: L أو 32)" class="bg-zinc-900 border border-zinc-700 rounded px-3 py-1.5 text-sm text-zinc-100 focus:outline-none focus:border-amber-400 w-full" required>
    </td>
    <td class="p-3">
      <input type="number" name="variant_stock[]" value="${stock}" min="0" class="bg-zinc-900 border border-zinc-700 rounded px-3 py-1.5 text-sm text-zinc-100 focus:outline-none focus:border-amber-400 w-24 text-center font-bold text-amber-400" required>
    </td>
    <td class="p-3 text-center">
      <button type="button" onclick="this.closest('tr').remove()" class="text-red-400 hover:text-red-300 p-1.5 transition">
        <i class="fas fa-trash-alt"></i>
      </button>
    </td>
  `;
  container.appendChild(row);
}

// Bulk generate variants for standard sizes
function generateStandardVariants(colorName, colorHex, sizes = ['S', 'M', 'L', 'XL', 'XXL'], defaultStock = 5) {
  sizes.forEach(s => {
    addVariantRow(colorName, colorHex, s, defaultStock);
  });
}

// Quick Stock Update in Inventory
async function quickUpdateStock(variantId, btnElement) {
  const input = document.getElementById(`stock-input-${variantId}`);
  if (!input) return;

  const stock = parseInt(input.value);
  if (isNaN(stock) || stock < 0) {
    alert('يرجى إدخال كمية صحيحة');
    return;
  }

  const originalHtml = btnElement.innerHTML;
  btnElement.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
  btnElement.disabled = true;

  try {
    const res = await fetch('/admin/inventory/update-stock', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ variant_id: variantId, stock: stock })
    });
    const data = await res.json();
    if (data.success) {
      btnElement.innerHTML = '<i class="fas fa-check text-green-400"></i>';
      setTimeout(() => {
        btnElement.innerHTML = originalHtml;
        btnElement.disabled = false;
      }, 1200);
    } else {
      alert(data.message || 'حدث خطأ أثناء التحديث.');
      btnElement.innerHTML = originalHtml;
      btnElement.disabled = false;
    }
  } catch (err) {
    alert('حدث خطأ في الاتصال بالخادم.');
    btnElement.innerHTML = originalHtml;
    btnElement.disabled = false;
  }
}

// Image preview handler
function previewImages(input) {
  const previewContainer = document.getElementById('image-preview-container');
  if (!previewContainer) return;

  if (input.files) {
    Array.from(input.files).forEach(file => {
      const reader = new FileReader();
      reader.onload = (e) => {
        const div = document.createElement('div');
        div.className = 'relative w-24 h-28 rounded-lg overflow-hidden border border-zinc-700 bg-zinc-900 group';
        div.innerHTML = `
          <img src="${e.target.result}" class="w-full h-full object-cover">
          <span class="absolute bottom-1 right-1 bg-amber-500/90 text-black text-[10px] font-bold px-1.5 py-0.5 rounded">جديد</span>
        `;
        previewContainer.appendChild(div);
      };
      reader.readAsDataURL(file);
    });
  }
}

