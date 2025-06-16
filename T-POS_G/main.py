from functools import wraps
from flask import Flask, render_template, request, redirect, session, flash, url_for, json
import pandas as pd
from datetime import datetime
import os
import sys
import random
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.wrappers import Response
import time

app = Flask(__name__)
app.secret_key = 'POS_1'
def get_base_dir():
    if getattr(sys, 'frozen', False):

        return os.path.dirname(sys.executable)
    else:
       
        return os.path.dirname(os.path.abspath(__file__))
BASE_DIR = get_base_dir()
PRODUCTS_FILE = os.path.join(BASE_DIR, 'products.xlsx')
SALES_FILE = os.path.join(BASE_DIR, 'sales.xlsx')
USERS_FILE = os.path.join(BASE_DIR, 'users.xlsx')

# ----------------------------- Helper Functions -----------------------------

def log_access(response):
    """Middleware untuk mencatat akses ke server"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ip = request.remote_addr
    user_agent = request.headers.get('User-Agent', 'Unknown')
    method = request.method
    path = request.path
    status = response.status_code
    
    log_entry = f"{ip}|{timestamp}|{user_agent}|{method}|{path}|{status}\n"
    
    with open("access_log.txt", "a") as f:
        f.write(log_entry)
    
    return response

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            flash("Anda harus login terlebih dahulu.", 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') != 'admin':
            flash("Anda tidak memiliki akses ke halaman ini.", 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def read_excel_file(file_path, columns):
    if os.path.exists(file_path):
        return pd.read_excel(file_path)
    else:
        return pd.DataFrame(columns=columns)

def read_users():
    return read_excel_file(USERS_FILE, ['username', 'password', 'role'])

def read_products():
    return read_excel_file(PRODUCTS_FILE, ['id', 'produk', 'harga', 'stok'])

def save_products(df):
    df.to_excel(PRODUCTS_FILE, index=False)

def read_sales():
    return read_excel_file(SALES_FILE, ['id_penjualan', 'id_produk', 'nama_produk', 'qty', 'harga', 'total_harga', 'tanggal', 'bulan', 'tahun'])

def save_sales(df):
    df.to_excel(SALES_FILE, index=False)

def init_products_file():
    if not os.path.exists(PRODUCTS_FILE):
        df = pd.DataFrame({
            'id': [1, 2, 3],
            'produk': ['Apple', 'Banana', 'Orange'],
            'harga': [10000, 7000, 12000],
            'stok': [50, 100, 70]
        })
        save_products(df)

def init_nota_file():
    if not os.path.exists(os.path.join(BASE_DIR, 'nota.xlsx')):
        df = pd.DataFrame(columns=[
            'id_nota', 'nama_pelanggan', 'nama_produk', 'qty', 'harga',
            'total_keranjang', 'potongan_harga', 'total_bayar', 'tanggal'
        ])
        df.to_excel(os.path.join(BASE_DIR, 'nota.xlsx'), index=False)

# ----------------------------- Routes: Authentication -----------------------------

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        users = read_users()
        user_row = users[users['username'] == username]
        if not user_row.empty and user_row.iloc[0]['password'] == password:
            session['username'] = username
            session['role'] = user_row.iloc[0]['role']
            flash('Login berhasil!', 'success')
            return redirect(url_for('index'))
        flash('Username atau password salah.', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("Anda berhasil logout.")
    return redirect(url_for('login'))

# ----------------------------- Routes: Home -----------------------------

@app.route('/')
@login_required
def index():
    products = read_products()
    cart_count = sum(item['qty'] for item in session.get('cart', {}).values())
    return render_template('index.html', products=products, cart_count=cart_count)

# ----------------------------- Routes: Cart -----------------------------

@app.route('/add/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    qty = int(request.form.get('qty', 1))
    products = read_products()
    product = products[products['id'] == product_id].squeeze()

    if qty < 1 or qty > int(product['stok']):
        flash("Jumlah tidak sesuai.")
        return redirect(url_for('index'))

    cart = session.get('cart', {})
    key = str(product_id)

    if key in cart:
        if cart[key]['qty'] + qty > int(product['stok']):
            flash(f"Stok tidak mencukupi untuk {product['produk']}.")
            return redirect(url_for('index'))
        cart[key]['qty'] += qty
    else:
        cart[key] = {
            'id': int(product['id']),
            'produk': str(product['produk']),
            'harga': float(product['harga']),
            'qty': int(qty)
        }

    session['cart'] = cart
    flash(f"{qty} x {product['produk']} ditambahkan ke keranjang.")
    return redirect(url_for('index'))

@app.route('/keranjang')
@login_required
def view_cart():
    cart = session.get('cart', {})
    total = sum(item['harga'] * item['qty'] for item in cart.values())
    return render_template('keranjang.html', cart=cart, total=total)

@app.route('/remove/<int:product_id>')
@login_required
def remove_from_cart(product_id):
    cart = session.get('cart', {})
    key = str(product_id)
    if key in cart:
        del cart[key]
        session['cart'] = cart
        flash("Produk dihapus dari keranjang.")
    return redirect(url_for('view_cart'))

@app.route('/clear_cart')
@login_required
def clear_cart():
    session.pop('cart', None)
    flash("Keranjang dikosongkan.")
    return redirect(url_for('view_cart'))

# ----------------------------- Routes: Checkout -----------------------------

@app.route('/checkout', methods=['POST'])
@login_required
def checkout():
    cart = session.get('cart', {})
    if not cart:
        flash("Keranjang kosong.")
        return redirect(url_for('view_cart'))

    try:
        potongan_harga = int(request.form.get('potongan_harga', 0))
    except ValueError:
        potongan_harga = 0

    nama_pelanggan = request.form.get('nama_pelanggan', 'Umum')

    products = read_products()

    for item in cart.values():
        row = products[products['id'] == item['id']].squeeze()
        if item['qty'] > row['stok']:
            flash(f"Stok tidak cukup untuk {item['produk']}")
            return redirect(url_for('view_cart'))

    for item in cart.values():
        idx = products.index[products['id'] == item['id']][0]
        products.at[idx, 'stok'] -= item['qty']

    total_keranjang = sum(item['qty'] * item['harga'] for item in cart.values())
    total_setelah_potongan = max(total_keranjang - potongan_harga, 0)

    # Simpan ke sales.xlsx (per produk)
    sales = read_sales()
    sale_id = 1 if sales.empty else sales['id_penjualan'].max() + 1
    now = datetime.now()

    new_sales = pd.DataFrame([{
        'id_penjualan': sale_id + i,
        'id_produk': item['id'],
        'nama_produk': item['produk'],
        'qty': item['qty'],
        'harga': item['harga'],
        'total_harga': item['qty'] * item['harga'],
        'tanggal': now.strftime('%Y-%m-%d'),
        'bulan': now.strftime('%B'),
        'tahun': now.year
    } for i, item in enumerate(cart.values())])

    save_sales(pd.concat([sales, new_sales], ignore_index=True))

    # Simpan ke nota.xlsx (per transaksi)
    try:
        nota = pd.read_excel('nota.xlsx')
    except FileNotFoundError:
        nota = pd.DataFrame(columns=[
            'id_nota', 'nama_pelanggan', 'nama_produk', 'qty', 'harga',
            'total_keranjang', 'potongan_harga', 'total_bayar', 'tanggal'])

    id_nota = 1 if nota.empty else nota['id_nota'].max() + 1

    new_nota = pd.DataFrame([{
        'id_nota': id_nota,
        'nama_pelanggan': nama_pelanggan,
        'nama_produk': item['produk'],
        'qty': item['qty'],
        'harga': item['harga'],
        'total_keranjang': total_keranjang,
        'potongan_harga': potongan_harga,
        'total_bayar': total_setelah_potongan,
        'tanggal': now.strftime('%Y-%m-%d')
    } for item in cart.values()])

    nota = pd.concat([nota, new_nota], ignore_index=True)
    nota.to_excel('nota.xlsx', index=False)

    save_products(products)
    session.pop('cart', None)
    flash("Checkout berhasil.")
    return redirect(url_for('index'))

@app.route('/search_products')
@login_required
def search_products():
    query = request.args.get('q', '').lower()
    products = read_products()
    if query:
        products = products[products['produk'].str.lower().str.contains(query)]
    return products.to_dict(orient='records')

# ----------------------------- Routes: Admin -----------------------------

@app.route('/admin')
@login_required
@admin_required
def admin():
    products = read_products()  # DataFrame
    search_query = request.args.get('q', '').lower()

    if search_query:
        products = products[
            products['produk'].str.lower().str.contains(search_query) |
            products['id'].astype(str).str.contains(search_query)
        ]

    # Pastikan hanya dict yang dikirim ke template
    return render_template('admin.html', products=products.to_dict(orient='records'))

@app.route('/admin/add', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_add():
    if request.method == 'POST':
        produk = request.form.get('produk')
        harga = request.form.get('harga')
        stok = request.form.get('stok')
        
        if not produk or not harga or not stok:
            flash("Semua field wajib diisi.")
            return render_template('admin_add.html')

        products = read_products()

        # Cek duplikat berdasarkan nama (case insensitive)
        if not products[products['produk'].str.lower() == produk.lower()].empty:
            flash("Produk sudah ada.", 'error')
            return render_template('admin_add.html')

        if products.empty:
            new_id = 1
        else:
            new_id = int(products['id'].max()) + 1

        try:
            harga = float(harga)
            stok = int(stok)
        except ValueError:
            flash("Harga harus angka dan stok harus integer.")
            return render_template('admin_add.html')

        new_product = pd.DataFrame([{
            'id': new_id,
            'produk': produk,
            'harga': harga,
            'stok': stok
        }])
        products = pd.concat([products, new_product], ignore_index=True)
        save_products(products)
        flash("Produk berhasil ditambahkan.")
        return redirect(url_for('admin'))
    
    return render_template('admin_add.html')

@app.route('/admin/edit/<int:product_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_edit(product_id):
    products = read_products()
    product_row = products.loc[products['id'] == product_id]
    if product_row.empty:
        flash("Produk tidak ditemukan.")
        return redirect(url_for('admin'))

    if request.method == 'POST':
        produk = request.form.get('produk')
        harga = request.form.get('harga')
        stok = request.form.get('stok')
        if not produk or not harga or not stok:
            flash("Semua field wajib diisi.")
            return redirect(url_for('admin_edit', product_id=product_id))

        try:
            harga = float(harga)
            stok = int(stok)
        except ValueError:
            flash("Harga harus angka dan stok harus integer.")
            return redirect(url_for('admin_edit', product_id=product_id))

        idx = products.index[products['id'] == product_id][0]
        products.at[idx, 'produk'] = produk
        products.at[idx, 'harga'] = harga
        products.at[idx, 'stok'] = stok
        save_products(products)
        flash("Produk berhasil diperbarui.")
        return redirect(url_for('admin'))

    product = product_row.iloc[0]
    return render_template('admin_edit.html', product=product)

@app.route('/admin/delete/<int:product_id>')
@login_required
@admin_required
def admin_delete(product_id):
    products = read_products()
    if product_id not in products['id'].values:
        flash("Produk tidak ditemukan.")
        return redirect(url_for('admin'))
    products = products[products['id'] != product_id]
    save_products(products)
    flash("Produk berhasil dihapus.")
    return redirect(url_for('admin'))

@app.route('/admin/sales')
@login_required
@admin_required
def admin_sales():
    sales = read_sales()

    
    filter_bulan = request.args.get('filter_bulan')
    filter_tahun = request.args.get('filter_tahun')

    if filter_bulan:
        sales = sales[sales['bulan'] == filter_bulan]
    if filter_tahun:
        sales = sales[sales['tahun'] == int(filter_tahun)]

    
    numeric_cols = [
        'qty', 'harga', 'total_harga',
        'potongan_harga', 'total_setelah_potongan',
        'total_bayar', 'kembalian'
    ]
    for col in numeric_cols:
        if col in sales.columns:
            sales[col] = pd.to_numeric(sales[col], errors='coerce').fillna(0)

    
    sales = sales.fillna('')

   
    sales_data = sales.to_dict(orient='records')

    return render_template(
        'admin_sales.html',
        sales=sales,
        sales_data=sales_data,
        datetime=datetime
    )


@app.route('/admin/sales/add', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_sales_add():
    products = read_products()
    if request.method == 'POST':
        id_produk = int(request.form.get('id_produk'))
        qty = int(request.form.get('qty'))

        product_row = products.loc[products['id'] == id_produk]
        if product_row.empty:
            flash("Produk tidak ditemukan.")
            return redirect(url_for('admin_sales_add'))

        produk = product_row.iloc[0]
        harga = produk['harga']
        total = harga * qty

        sales = read_sales()
        new_id = 1 if sales.empty else int(sales['id_penjualan'].max()) + 1

        new_sale = pd.DataFrame([{
            'id_penjualan': new_id,
            'id_produk': id_produk,
            'nama_produk': produk['produk'],
            'qty': qty,
            'harga': harga,
            'total_harga': total,
            'tanggal': datetime.now().strftime('%Y-%m-%d'),
            'bulan': datetime.now().strftime('%B'),
            'tahun': datetime.now().year
        }])
        sales = pd.concat([sales, new_sale], ignore_index=True)
        save_sales(sales)
        flash("Penjualan berhasil ditambahkan.")
        return redirect(url_for('admin_sales'))
    return render_template('admin_sales_add.html', products=products)

@app.route('/admin/sales/delete/<int:sale_id>')
@login_required
@admin_required
def admin_sales_delete(sale_id):
    sales = read_sales()
    if sale_id not in sales['id_penjualan'].values:
        flash("Penjualan tidak ditemukan.")
        return redirect(url_for('admin_sales'))
    sales = sales[sales['id_penjualan'] != sale_id]
    save_sales(sales)
    flash("Penjualan berhasil dihapus.")
    return redirect(url_for('admin_sales'))

@app.route('/nota')
@login_required
def view_nota():
    try:
        # Mencoba membaca file Excel
        df = pd.read_excel('nota.xlsx')
        
        # Jika file ada tapi kosong
        if df.empty:
            flash('File nota.xlsx ada tetapi tidak berisi data', 'warning')
            return render_template('nota.html', notas={})
            
    except FileNotFoundError:
        # Jika file tidak ditemukan
        flash('File nota.xlsx tidak ditemukan', 'danger')
        return render_template('nota.html', notas={})
        
    except Exception as e:
        # Menangani error lainnya
        flash(f'Terjadi error saat membaca file: {str(e)}', 'danger')
        return render_template('nota.html', notas={})

    # Proses pencarian
    search_query = request.args.get('q', '').lower()
    notas = {}
    
    try:
        if not df.empty:
            if search_query:
                df = df[
                    df['id_nota'].astype(str).str.contains(search_query, case=False) |
                    df['nama_pelanggan'].str.lower().str.contains(search_query)
                ]

            # Pastikan kolom yang diperlukan ada
            required_columns = ['id_nota', 'nama_pelanggan', 'tanggal', 'total_keranjang', 
                              'potongan_harga', 'total_bayar', 'nama_produk', 'qty', 'harga']
            
            if not all(col in df.columns for col in required_columns):
                missing = [col for col in required_columns if col not in df.columns]
                flash(f'Kolom yang diperlukan tidak ditemukan: {", ".join(missing)}', 'danger')
                return render_template('nota.html', notas={})

            grouped = df.groupby('id_nota')
            for nota_id, group in grouped:
                transaksi = {
                    'nama_pelanggan': group['nama_pelanggan'].iloc[0],
                    'tanggal': group['tanggal'].iloc[0],
                    'total_keranjang': group['total_keranjang'].iloc[0],
                    'potongan_harga': group['potongan_harga'].iloc[0],
                    'total_bayar': group['total_bayar'].iloc[0],
                    'produk': group[['nama_produk', 'qty', 'harga']].to_dict('records')
                }
                notas[nota_id] = transaksi
                
            # Mengurutkan nota
            try:
                sorted_notas = dict(sorted(
                    notas.items(),
                    key=lambda x: int(x[0]),
                    reverse=True
                ))
            except (ValueError, TypeError):
                # Jika id_nota tidak bisa di-convert ke int, sort sebagai string
                sorted_notas = dict(sorted(
                    notas.items(),
                    key=lambda x: str(x[0]),
                    reverse=True
                ))
                
            return render_template('nota.html', notas=sorted_notas)
            
    except Exception as e:
        flash(f'Terjadi error saat memproses data: {str(e)}', 'danger')
        return render_template('nota.html', notas={})
        
    # Fallback jika semua else gagal
    return render_template('nota.html', notas={})

@app.route('/nota/<int:id_nota>')
@login_required
def cetak_nota(id_nota):
    try:
        df = pd.read_excel('nota.xlsx')
    except FileNotFoundError:
        flash("Data nota tidak ditemukan.")
        return redirect(url_for('view_nota'))

    df_nota = df[df['id_nota'] == id_nota]
    if df_nota.empty:
        flash("Nota tidak ditemukan.")
        return redirect(url_for('view_nota'))

    produk_list = df_nota[['nama_produk', 'qty', 'harga']].to_dict('records')
    
  
    for item in produk_list:
        item['subtotal'] = item['qty'] * item['harga']

    tanggal = df_nota['tanggal'].iloc[0]
    if isinstance(tanggal, pd.Timestamp):
        tanggal = tanggal.strftime('%d/%m/%Y')  

    transaksi = {
        'id_nota': id_nota,
        'nama_pelanggan': df_nota['nama_pelanggan'].iloc[0] or "Umum",
        'tanggal': tanggal,
        'total_keranjang': df_nota['total_keranjang'].iloc[0],
        'potongan_harga': df_nota['potongan_harga'].iloc[0] or 0,
        'total_bayar': df_nota['total_bayar'].iloc[0],
        'produk': produk_list,
        'rand': f"{random.randint(1000, 9999)} - {random.randint(1000, 9999)}"
    }

    return render_template('cetak_nota.html', transaksi=transaksi)



# ----------------------------- Routes: Laporan Penjualan -----------------------------

@app.route('/laporan', methods=['GET', 'POST'])
@login_required
@admin_required
def laporan():
    sales = read_sales()
    filtered_sales = pd.DataFrame()
    total_penjualan = 0
    tanggal_awal = tanggal_akhir = ''

    if request.method == 'POST':
        tanggal_awal = request.form.get('tanggal_awal')
        tanggal_akhir = request.form.get('tanggal_akhir')

        if tanggal_awal and tanggal_akhir:
            sales['tanggal'] = pd.to_datetime(sales['tanggal'])
            start = pd.to_datetime(tanggal_awal)
            end = pd.to_datetime(tanggal_akhir)

            filtered_sales = sales[(sales['tanggal'] >= start) & (sales['tanggal'] <= end)]
            total_penjualan = filtered_sales['total_harga'].sum()

    return render_template('laporan.html',
                           sales=filtered_sales.to_dict(orient='records'),
                           total=total_penjualan,
                           tanggal_awal=tanggal_awal,
                           tanggal_akhir=tanggal_akhir)

# ----------------------------- Entry Point -----------------------------

if __name__ == '__main__':
    init_products_file()
    @app.after_request
    def log_access(response):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ip = request.remote_addr
        user_agent = request.headers.get('User-Agent', 'Unknown')
        method = request.method
        path = request.path
        status = response.status_code
    
        log_entry = f"{ip}|{timestamp}|{user_agent}|{method}|{path}|{status}\n"
    
        with open("access_log.txt", "a") as f:
            f.write(log_entry)
        return response
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)