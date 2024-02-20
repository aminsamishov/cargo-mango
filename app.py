import datetime
from io import BytesIO
import secrets
from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for
from dotenv import load_dotenv
import os
import psycopg2
import xlsxwriter
import psycopg2.extras
from sqlalchemy import create_engine
import pandas as pd
import psycopg2
from io import StringIO
from werkzeug.utils import secure_filename
import logging
from psycopg2.extras import DictCursor
load_dotenv()

app = Flask(__name__)
app.config['STATIC_FOLDER'] = 'static'

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'xlsx', 'xls'}

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

#--------------INDEX----------------------
@app.route('/')
def main():
    fonts = {'icomoon': {'style': 'fonts/icomoon/style.css'}}
    return render_template('main.html', fonts=fonts)


@app.route('/admin')
def admin_page():
    return render_template('dashboard.html')

def get_database_connection():
    database_url = os.environ.get('DATABASE_URL')
    connection = psycopg2.connect(database_url)
    return connection

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
@app.route('/upload_data', methods=['POST'])
def upload_data_to_db():
    if 'file' not in request.files:
        return jsonify({'error': 'Файл не найден'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Файл не выбран'}), 400

    try:
        df = pd.read_excel(file)
    except Exception as e:
        logging.error(f'Ошибка при чтении Excel файла: {e}')
        return jsonify({'error': 'Ошибка при чтении Excel файла'}), 500

    try:
        selected_columns = ['data_send_from_china', 'user_id', 'track_code', 'order_status_id']
        df = df[selected_columns]
    except Exception as e:
        logging.error(f'Ошибка при выборе столбцов: {e}')
        return jsonify({'error': 'Ошибка при выборе столбцов'}), 500

    try:
        buffer = StringIO()
        df.to_csv(buffer, index=False, header=False, sep='\t')
        buffer.seek(0)
    except Exception as e:
        error_message = f'Ошибка при подготовке данных для загрузки:{str(e)}'
        logging.error(error_message)
        return jsonify({'error': error_message}), 500

    try:
        connection = get_database_connection()
        cursor = connection.cursor()
        cursor.copy_expert("COPY \"Order\" (data_send_from_china, user_id, track_code, order_status_id) FROM STDIN WITH CSV DELIMITER '\t'", buffer)
        connection.commit()
    except Exception as e:
        error_message = f'Ошибка при загрузке данных в базу данных: {str(e)}'
        logging.error(error_message)
        return jsonify({'error': error_message}), 500
    return jsonify({'message': 'Данные успешно загружены'}), 200


#-----------------------SORTING----------------------------------------
    
@app.route('/sorting')
def sorting_page():
    return render_template('sorting.html')

@app.route('/get_order_details', methods=['POST'])
def get_order_details():
    track_code = request.form.get('trackCode')
    if not track_code:
        logging.error('Трек-код не предоставлен')
        return jsonify({'error': 'Трек-код не предоставлен'}), 400

    try:
        conn = get_database_connection()
        cur = conn.cursor(cursor_factory=DictCursor)

        cur.execute('''
    SELECT o.data_send_from_china, o.user_id, o.track_code, os.name AS order_status,
           COALESCE(o.price, t.price) AS tarif_price, t.name AS tarif_name, o.massa, o.comment, o.sort_date
    FROM "Order" o
    JOIN Order_status os ON o.order_status_id = os.id
    LEFT JOIN Tarif t ON t.id = COALESCE(o.tarif_id, 1)  
    WHERE o.track_code = %s
''', (track_code,))




        order = cur.fetchone()
    except Exception as e:
        logging.error(f'Ошибка при запросе к базе данных: {e}')
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    finally:
        cur.close()
        conn.close()

    if order:
        order_details = {
        'data_send_from_china': order['data_send_from_china'].strftime('%Y-%m-%d') if order['data_send_from_china'] else 'Не указано',
        'user_id': order['user_id'],
        'track_code': order['track_code'],
        'order_status': order['order_status'],
        'tarif_name': order['tarif_name'],
        'tarif_price': str(order['tarif_price']),
        'massa': order['massa'],
        'comment': order['comment'],
        'sort_date': order['sort_date']
    }
        return jsonify(order_details)

    else:
        logging.error('Заказ с таким трек-кодом не найден')
        return jsonify({'error': 'Заказ с таким трек-кодом не найден'}), 404


@app.route('/save_order_details', methods=['POST'])
def save_order_details():
    data = request.json
    track_code = data.get('track_code')
    price = data.get('price')
    tarif_id = data.get('tarif_id')
    user_id = data.get('user_id')
    massa = data.get('massa')
    has_obreshetka = data.get('has_obreshetka')
    dlina = data.get('dlina') if data.get('dlina') else None
    shirina = data.get('shirina') if data.get('shirina') else None
    glubina = data.get('glubina') if data.get('glubina') else None
    comment = data.get('comment')

    if not track_code:
        logging.error('Трек-код не предоставлен')
        return jsonify({'error': 'Трек-код не предоставлен'}), 400

    try:
        conn = get_database_connection()
        cur = conn.cursor()

        # Если price не указан, получаем значение по умолчанию из таблицы Tarif
        if price is None:
            cur.execute('SELECT id, price FROM Tarif WHERE id = 1')
            tarif_default = cur.fetchone()
            tarif_id = tarif_default[0]
            price = tarif_default[1]

        # Расчёт общей суммы
        amount = float(massa) * float(price)

        # Обновление заказа с новыми данными
        cur.execute('''
            UPDATE "Order"
            SET user_id=%s, massa=%s, price=%s, amount=%s, has_obreshetka=%s, dlina=%s, shirina=%s, glubina=%s, comment=%s, order_status_id=2, sort_date=CURRENT_TIMESTAMP, tarif_id=%s
            WHERE track_code=%s
        ''', (user_id, massa, price, amount, has_obreshetka, dlina, shirina, glubina, comment, tarif_id, track_code))

        conn.commit()
    except Exception as e:
        logging.error(f'Ошибка при обновлении данных заказа: {e}')
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    finally:
        cur.close()
        conn.close()

    return jsonify({'success': 'Данные заказа успешно обновлены'})

@app.route('/finish_sorting', methods=['POST'])
def finish_sorting():
    try:
        conn = get_database_connection()
        cur = conn.cursor()

        # Изменяем статус с 2 на 3 для всех заказов
        cur.execute('UPDATE "Order" SET order_status_id = 3 WHERE order_status_id = 2 RETURNING id')
        affected_rows = cur.rowcount  # Количество измененных строк

        conn.commit()
        return jsonify({'message': f'{affected_rows} заказов отсортировано'})
    except Exception as e:
        logging.error(f'Ошибка при обновлении статусов заказов: {e}')
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    finally:
        cur.close()
        conn.close()


#-------------orders-----------------------
        
@app.route('/orders')
def orders_page():
    return render_template('orders.html')

@app.route('/get_all_orders', methods=['GET'])
def get_all_orders():
    try:
        conn = get_database_connection()
        cur = conn.cursor(cursor_factory=DictCursor)

        cur.execute('''
            SELECT 
                o.data_send_from_china, o.track_code, os.name AS order_status, 
                COALESCE(o.price, t.price) AS tarif_price, t.name AS tarif_name, 
                o.massa, o.comment, o.sort_date, o.amount,
                u.name || ' ' || u.surname AS client_fio, u.id AS user_id, 
                c.name AS city_name, 
                ct.phone_num, ct.extra_phone_num, ct.tg_nickname, ct.email,
                CASE 
                    WHEN t.id = 1 THEN ((t.price - COALESCE(o.price, t.price)) / t.price * 100) 
                    ELSE NULL 
                END AS discount
            FROM "Order" o
            JOIN Order_status os ON o.order_status_id = os.id
            LEFT JOIN Tarif t ON t.id = COALESCE(o.tarif_id, 1)
            LEFT JOIN "User" u ON o.user_id = u.id
            LEFT JOIN City c ON u.city_id = c.id
            LEFT JOIN Contact ct ON u.id = ct.user_id
        ''')

        orders = cur.fetchall()
    except Exception as e:
        logging.error(f'Ошибка при запросе к базе данных: {e}')
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    finally:
        cur.close()
        conn.close()

    orders_data = []
    for order in orders:
        order_details = {
            'data_send_from_china': order['data_send_from_china'].strftime('%Y-%m-%d') if order['data_send_from_china'] else 'Не указано',
            'track_code': order['track_code'],
            'order_status': order['order_status'],
            'tarif_name': order['tarif_name'],
            'tarif_price': str(order['tarif_price']),
            'massa': order['massa'],
            'comment': order['comment'],
            'client_fio': order['client_fio'],
            'user_id': order['user_id'],
            'city_name': order['city_name'],
            'phone_num': order['phone_num'],
            'extra_phone_num': order['extra_phone_num'],
            'tg_nickname': order['tg_nickname'],
            'email': order['email'],
            'sort_date': order['sort_date'].strftime('%Y-%m-%d %H:%M:%S') if order['sort_date'] else 'Не указано',
            'amount': str(order['amount']),
            'discount': '{:.2f}%'.format(order['discount']) if order['discount'] is not None else 'Не расчитано'
        }
        orders_data.append(order_details)

    return jsonify(orders_data)


#-------------USERS---------------
@app.route('/manage_users')
def manage_users():

    return render_template('manage_users.html')  

@app.route('/get_all_users', methods=['GET'])
def get_all_users():
    try:
        conn = get_database_connection()
        cur = conn.cursor(cursor_factory=DictCursor)

        cur.execute('''
            SELECT 
                u.id, u.name, u.surname, 
                c.name AS city_name, 
                ct.phone_num, ct.extra_phone_num, ct.tg_nickname, ct.email
            FROM "User" u
            LEFT JOIN City c ON u.city_id = c.id
            LEFT JOIN Contact ct ON u.id = ct.user_id
        ''')

        users = cur.fetchall()
    except Exception as e:
        logging.error(f'Ошибка при запросе к базе данных: {e}')
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    finally:
        cur.close()
        conn.close()

    users_data = []
    for user in users:
        user_details = {
            'id': user['id'],
            'name': user['name'],
            'surname': user['surname'],
            'city_name': user['city_name'],
            'phone_num': user['phone_num'],
            'extra_phone_num': user['extra_phone_num'],
            'tg_nickname': user['tg_nickname'],
            'email': user['email']
        }
        users_data.append(user_details)
        

    return jsonify(users_data)


@app.route('/get_user_by_id/<user_id>', methods=['GET'])
def get_user_by_id(user_id):
    try:
        conn = get_database_connection()
        cur = conn.cursor(cursor_factory=DictCursor)

        cur.execute('''
            SELECT
                u.id, u.name, u.surname,
                c.name AS city_name,
                ct.phone_num, ct.extra_phone_num, ct.tg_nickname, ct.email
            FROM "User" u
            LEFT JOIN City c ON u.city_id = c.id
            LEFT JOIN Contact ct ON u.id = ct.user_id
            WHERE u.id = %s
        ''', (user_id,))

        user = cur.fetchone()
        if not user:
            return jsonify({'error': 'Пользователь не найден'}), 404

        user_data = {
            'id': user['id'],
            'name': user['name'],
            'surname': user['surname'],
            'city_name': user['city_name'],
            'phone_num': user['phone_num'],
            'extra_phone_num': user['extra_phone_num'],
            'tg_nickname': user['tg_nickname'],
            'email': user['email']
        }

        return jsonify(user_data)
    except Exception as e:
        logging.error(f'Ошибка при запросе к базе данных: {e}')
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    finally:
        cur.close()
        conn.close()



@app.route('/update_user', methods=['POST'])
def update_user():
    data = request.json
    user_id = data.get('id')

    try:
        conn = get_database_connection()
        cur = conn.cursor()

        cur.execute('''
            UPDATE "User"
            SET name = %s, surname = %s
            WHERE id = %s
        ''', (data['name'], data['surname'], user_id))

        conn.commit()

        return jsonify({'success': True, 'message': 'Данные пользователя обновлены'})
    except Exception as e:
        conn.rollback()
        logging.error(f'Ошибка при обновлении данных пользователя: {e}')
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    finally:
        cur.close()
        conn.close()

#-----------PAYMENT---------------------
        
@app.route('/payment')
def payment_page():

    return render_template('payment.html')

@app.route('/get_user_orders/<int:user_id>', methods=['GET'])
def get_user_orders(user_id):
    try:
        conn = get_database_connection()
        cur = conn.cursor(cursor_factory=DictCursor)

        cur.execute('''
            SELECT o.data_send_from_china, o.track_code, os.name AS order_status, 
                   COALESCE(o.price, t.price) AS tarif_price, t.name AS tarif_name, 
                   o.massa, o.comment, o.sort_date, o.amount,
                   u.name || ' ' || u.surname AS client_fio, u.id AS user_id, 
                   c.name AS city_name, 
                   ct.phone_num, ct.extra_phone_num, ct.tg_nickname, ct.email,
                   CASE 
                       WHEN t.id = 1 THEN ((t.price - COALESCE(o.price, t.price)) / t.price * 100) 
                       ELSE NULL 
                   END AS discount
            FROM "Order" o
            JOIN Order_status os ON o.order_status_id = os.id
            LEFT JOIN Tarif t ON t.id = COALESCE(o.tarif_id, 1)
            LEFT JOIN "User" u ON o.user_id = u.id
            LEFT JOIN City c ON u.city_id = c.id
            LEFT JOIN Contact ct ON u.id = ct.user_id
            WHERE o.user_id = %s AND o.order_status_id = 3
        ''', (user_id,))

        orders = cur.fetchall()
    except Exception as e:
        logging.error(f'Ошибка при запросе к базе данных: {e}')
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    finally:
        cur.close()
        conn.close()

    orders_data = [dict(order) for order in orders]
    return jsonify(orders_data)

@app.route('/update_orders', methods=['POST'])
def update_orders():
    user_id = request.form.get('user_id')

    try:
        conn = get_database_connection()  # Замените на свой метод подключения к базе данных
        cur = conn.cursor()

        # Обновляем статус и вставляем текущую дату в поле pay_date для всех заказов пользователя
        cur.execute('''
            UPDATE "Order"
            SET order_status_id = 4, pay_date = %s
            WHERE user_id = %s AND order_status_id = 3
        ''', (datetime.datetime.now(), user_id))  # Поместите datetime.datetime.now() в кортеж

        conn.commit()
        return 'Заказы успешно обновлены'
    except Exception as e:
        logging.error(f'Ошибка при обновлении заказов: {e}')
        return jsonify({'error': 'Ошибка при обновлении заказов'}), 500
    finally:
        cur.close()
        conn.close()


@app.route('/order_status_statistics')
def order_status_statistics():
    conn = get_database_connection()
    cur = conn.cursor()

    try:
        cur.execute('''
            SELECT os.name AS status, COUNT(*) AS count
            FROM "Order" o
            JOIN Order_status os ON o.order_status_id = os.id
            GROUP BY os.name
        ''')
        rows = cur.fetchall()
        statistics = {status: count for status, count in rows}
        return jsonify(statistics)
    except psycopg2.Error as e:
        print("Error fetching order status statistics:", e)
    finally:
        cur.close()
        conn.close()

@app.route('/stat')
def index():
    return render_template('search_user.html')       

# Маршрут для получения статистики по количеству заказов в разрезе городов
@app.route('/city_order_statistics')
def city_order_statistics():
    try:
        conn = get_database_connection()
        cur = conn.cursor()

        cur.execute('''
            SELECT c.name, COUNT(o.id) as order_count
            FROM "Order" o
            JOIN "User" u ON o.user_id = u.id
            JOIN City c ON u.city_id = c.id
            GROUP BY c.name
        ''')

        data = cur.fetchall()
        city_order_statistics = {city: count for city, count in data}

        return jsonify(city_order_statistics)

    except Exception as e:
        return jsonify({'error': str(e)})

    finally:
        cur.close()
        conn.close()

# Маршрут для получения статистики по средней стоимости заказов по тарифам
@app.route('/tarif_cost_statistics')
def tarif_cost_statistics():
    try:
        conn = get_database_connection()
        cur = conn.cursor()

        cur.execute('''
            SELECT t.name, AVG(o.amount) as average_cost
            FROM "Order" o
            JOIN Tarif t ON o.tarif_id = t.id
            GROUP BY t.name
        ''')

        data = cur.fetchall()
        tarif_cost_statistics = {tarif: cost for tarif, cost in data}

        return jsonify(tarif_cost_statistics)

    except Exception as e:
        return jsonify({'error': str(e)})

    finally:
        cur.close()
        conn.close()

@app.route('/city_order_statistics')
def get_city_order_statistics():
    try:
        conn = get_database_connection()
        cur = conn.cursor()

        cur.execute('''
            SELECT c.name, COUNT(o.id) as order_count
            FROM "Order" o
            JOIN "User" u ON o.user_id = u.id
            JOIN City c ON u.city_id = c.id
            GROUP BY c.name
        ''')

        data = cur.fetchall()
        city_order_statistics = {city: count for city, count in data}

        return jsonify(city_order_statistics)

    except Exception as e:
        return jsonify({'error': str(e)})

    finally:
        cur.close()
        conn.close()

# Получение статистики средней стоимости заказов по тарифам
@app.route('/tarif_cost_statistics')
def get_tarif_cost_statistics():
    try:
        conn = get_database_connection()
        cur = conn.cursor()

        cur.execute('''
            SELECT t.name, AVG(o.amount) as average_cost
            FROM "Order" o
            JOIN Tarif t ON o.tarif_id = t.id
            GROUP BY t.name
        ''')

        data = cur.fetchall()
        tarif_cost_statistics = {tarif: cost for tarif, cost in data}

        return jsonify(tarif_cost_statistics)

    except Exception as e:
        return jsonify({'error': str(e)})

    finally:
        cur.close()
        conn.close()

# Получение статистики по распределению заказов по времени отправки из Китая
@app.route('/send_date_statistics')
def get_send_date_statistics():
    try:
        conn = get_database_connection()
        cur = conn.cursor()

        cur.execute('''
            SELECT DATE(data_send_from_china), COUNT(id) as order_count
            FROM "Order"
            GROUP BY DATE(data_send_from_china)
        ''')

        data = cur.fetchall()
        send_date_statistics = {str(date): count for date, count in data}

        return jsonify(send_date_statistics)

    except Exception as e:
        return jsonify({'error': str(e)})

    finally:
        cur.close()
        conn.close()

# def create_user_in_database(name, surname, city_id, phone_num, extra_phone_num, tg_nickname, email):
#     connection = get_database_connection()
#     cursor = connection.cursor()

#     password = secrets.token_urlsafe(8)
#     login = f"user_{secrets.randbelow(1000)}"

#     cursor.execute("""
#         INSERT INTO "User" (name, surname, city_id, login, password)
#         VALUES (%s, %s, %s, %s, %s)
#         RETURNING id
#     """, (name, surname, city_id, login, password))

#     user_id = cursor.fetchone()[0]

#     cursor.execute("""
#         INSERT INTO Contact (phone_num, extra_phone_num, tg_nickname, email, user_id)
#         VALUES (%s, %s, %s, %s, %s)
#     """, (phone_num, extra_phone_num, tg_nickname, email, user_id))

#     connection.commit()
#     cursor.close()
#     connection.close()


# def search_user_by_name(search_query):
#     connection = get_database_connection()
#     cursor = connection.cursor()

#     try:
#         cursor.execute("""
#             SELECT u.id AS user_id, u.name, u.surname, city.name AS city_name,
#                    c.id AS contact_id, c.phone_num, c.extra_phone_num, c.tg_nickname, c.email
#             FROM "User" u
#             LEFT JOIN Contact c ON u.id = c.user_id
#             LEFT JOIN City ON u.city_id = city.id
#             WHERE u.name ILIKE %s OR u.surname ILIKE %s
#         """, ('%' + search_query + '%', '%' + search_query + '%'))

#         rows = cursor.fetchall()

#         columns = ["user_id", "name", "surname", "city_name", "contact_id", "phone_num", "extra_phone_num", "tg_nickname", "email"]
#         df = pd.DataFrame(rows, columns=columns)

#         return df

#     except Exception as e:
#         print(f"Error: {e}")
#         return pd.DataFrame()

#     finally:
#         cursor.close()
#         connection.close()

# def fetch_user_by_id(user_id):
#     connection = get_database_connection()
#     cursor = connection.cursor()

#     try:
#         cursor.execute("""
#             SELECT u.id AS user_id, u.name, u.surname, city.name AS city_name,
#                    c.id AS contact_id, c.phone_num, c.extra_phone_num, c.tg_nickname, c.email
#             FROM "User" u
#             LEFT JOIN Contact c ON u.id = c.user_id
#             LEFT JOIN City ON u.city_id = city.id
#             WHERE u.id = %s
#         """, (user_id,))

#         rows = cursor.fetchall()

#         columns = ["user_id", "name", "surname", "city_name", "contact_id", "phone_num", "extra_phone_num", "tg_nickname", "email"]
#         df = pd.DataFrame(rows, columns=columns)

#         return df.iloc[0] if not df.empty else pd.DataFrame()

#     except Exception as e:
#         print(f"Error: {e}")
#         return pd.DataFrame()

#     finally:
#         cursor.close()
#         connection.close()

# def update_user_data(user_id, new_name, new_surname):
#     connection = get_database_connection()
#     cursor = connection.cursor()

#     try:
#         cursor.execute("""
#             UPDATE "User"
#             SET name = %s, surname = %s
#             WHERE id = %s
#         """, (new_name, new_surname, user_id))

#         connection.commit()


#     except Exception as e:
#         print(f"Error: {e}")
#         connection.rollback()

#     finally:
#         cursor.close()
#         connection.close()


# @app.route('/admin/search_user', methods=['GET', 'POST'])
# def search_user():
#     if request.method == 'POST':
#         search_query = request.form.get('search_query')
#         users = search_user_by_name(search_query)
#         return render_template('admin#order-payment.html', users=users)

   

# @app.route('/admin/edit_user/<int:user_id>', methods=['GET', 'POST'])
# def edit_user(user_id):
#     user_data = fetch_user_by_id(user_id)

#     if request.method == 'POST':
#         new_name = request.form.get('new_name')
#         new_surname = request.form.get('new_surname')
#         update_user_data(user_id, new_name, new_surname)
#         return redirect(url_for('user_management'))

#     return render_template('edit_user.html', user_data=user_data)

# @app.route('/create_user_form', methods=['GET'])
# def create_user_form():
#     cities = get_cities()
#     return render_template('create_user_form.html', cities=cities)

# @app.route('/create_user', methods=['POST'])
# def create_user():
#     name = request.form.get('name')
#     surname = request.form.get('surname')
#     city_id = request.form.get('city_id')
#     phone_num = request.form.get('phone_num')
#     extra_phone_num = request.form.get('extra_phone_num')
#     tg_nickname = request.form.get('tg_nickname')
#     email = request.form.get('email')

#     create_user_in_database(name, surname, city_id, phone_num, extra_phone_num, tg_nickname, email)

#     users_data = get_users_data()

#     return render_template('users_table.html', users_data=users_data)

# def get_cities():
#     connection = get_database_connection()
#     cursor = connection.cursor()

#     cursor.execute("SELECT id, name FROM City")
#     cities = cursor.fetchall()

#     cursor.close()
#     connection.close()

#     return cities

# def get_users_data():
#     connection = get_database_connection()
#     cursor = connection.cursor()

#     cursor.execute("""
#         SELECT u.id, u.name, u.surname, u.login, u.password, c.phone_num, c.extra_phone_num, c.tg_nickname, c.email
#         FROM "User" u
#         LEFT JOIN Contact c ON u.id = c.user_id
#     """)
    
#     data = cursor.fetchall()

#     cursor.close()
#     connection.close()

#     return data


# def upload_data_to_db(file_path):
#     try:
#         connection = get_database_connection()
#         cursor = connection.cursor()

#         df = pd.read_excel(file_path)

#         selected_columns = ['data_send_from_china', 'user_id', 'track_code', 'order_status_id']
#         df = df[selected_columns]

#         buffer = StringIO()
#         df.to_csv(buffer, index=False, header=False, sep='\t')
#         buffer.seek(0)

#         cursor.copy_expert("COPY \"Order\" (data_send_from_china, user_id, track_code, order_status_id) FROM STDIN WITH CSV HEADER DELIMITER '\t'", buffer)

#         connection.commit()
#         print("Data successfully uploaded to the 'Order' table.")
#     except Exception as e:
#         print(f"Error during data upload: {e}")


# def get_order_data():
#     try:
#         connection = get_database_connection()
#         cursor = connection.cursor()

#         cursor.execute("SELECT * FROM \"Order\"")
#         data = cursor.fetchall()

        
#         print(f"Retrieved data from the 'Order' table: {data}")
#         return data
#     except Exception as e:
#         print(f"Error during data retrieval: {e}")
    

#     finally:
#         if cursor:
#             cursor.close()
#         if connection:
#             connection.close()

# def allowed_file(filename):
#     return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# @app.route('/admin/upload', methods=['GET', 'POST'])
# def upload_file():
#     if request.method == 'POST':
#         file = request.files['file']
#         if file and allowed_file(file.filename):
#             filename = secure_filename(file.filename)
#             file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
#             file.save(file_path)

#             upload_data_to_db(file_path)

#             order_data = get_order_data()

#             return render_template('order_table.html', order_data=order_data)

#     return render_template('admin.html')





# def fetch_user_and_contacts_data():
#     connection = get_database_connection()
#     cursor = connection.cursor()

#     try:
#         cursor.execute("""
#             SELECT u.id AS user_id, u.name, u.surname, city.name AS city_name,
#                    c.id AS contact_id, c.phone_num, c.extra_phone_num, c.tg_nickname, c.email
#             FROM "User" u
#             LEFT JOIN Contact c ON u.id = c.user_id
#             LEFT JOIN City ON u.city_id = city.id
#         """)

#         rows = cursor.fetchall()

#         columns = ["user_id", "name", "surname", "city_name", "contact_id", "phone_num", "extra_phone_num", "tg_nickname", "email"]
#         df = pd.DataFrame(rows, columns=columns)

#         return df

#     except Exception as e:
#         print(f"Error: {e}")
#         return pd.DataFrame()  

#     finally:
#         cursor.close()
#         connection.close()

# import openpyxl
# from openpyxl.utils.dataframe import dataframe_to_rows

# def create_excel_file(data):
#     wb = openpyxl.Workbook()
#     ws = wb.active

#     for row in dataframe_to_rows(data, index=False, header=True):
#         ws.append(row)

#     output = BytesIO()
#     wb.save(output)
#     output.seek(0)
    
#     return output

# @app.route('/admin/download_excel')
# def download_excel():
#     users = fetch_user_and_contacts_data()
#     excel_data = create_excel_file(users)
#     return send_file(excel_data, download_name='user_and_contacts_data.xlsx', as_attachment=True)


# # @app.route('/')
# # def index():
# #     data = fetch_user_and_contacts_data()
# #     return render_template('index.html', data=data)

# # @app.route('/download_excel')
# # def download_excel():
# #     data = fetch_user_and_contacts_data()
# #     excel_data = create_excel_file(data)
# #     return send_file(excel_data, download_name='user_and_contacts_data.xlsx', as_attachment=True)


# # @app.route('/admin1')
# # def admin_page():
# #     return render_template('admin1.html')


# # @app.route('/admin')
# # def admin():
# #     data = fetch_user_and_contacts_data()
# #     return render_template('admin.html', users=data)




# @app.route('/tables')
# def list_tables():
#     try:
#         with get_database_connection() as connection, connection.cursor() as cursor:
#             cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public';")
#             tables = cursor.fetchall()

#         table_names = [table[0] for table in tables]

#         return render_template('tables.html', tables=table_names)

#     except Exception as e:
#         return jsonify({'error': str(e)})

# if __name__ == '__main__':
#     app.run(debug=True)
if __name__ == '__main__':
    app.run(debug=True)