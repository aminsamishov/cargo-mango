import concurrent.futures
import requests

def send_get_request(url):
    response = requests.get(url)
    return {
        'url': url,
        'status_code': response.status_code,
        'response_time': response.elapsed.total_seconds(),
        'error_message': response.text if response.status_code != 200 else None
    }

def send_post_request(url, data):
    response = requests.post(url, json=data)
    return {
        'url': url,
        'status_code': response.status_code,
        'response_time': response.elapsed.total_seconds(),
        'error_message': response.text if response.status_code != 200 else None
    }

urls = [
   
    "http://176.126.166.199:8080/get_all_orders"
]

data = {
    "name": "John",
    "surname": "Doe",
    "city_id": 1,
    "phone_number": "123456789",
    "login": "johndoe",
    "password": "password"
}

# Функция для выполнения запросов определенное количество раз и вывода результатов
def execute_requests(url):
    results = []
    for _ in range(1000):
        if url == "http://176.126.166.199:8080/get_all_orders":
            result = send_post_request(url, data)
        else:
            result = send_get_request(url)
        results.append(result)
    return results

# Выполнение запросов с использованием ThreadPoolExecutor
with concurrent.futures.ThreadPoolExecutor() as executor:
    all_results = executor.map(execute_requests, urls)

# Обработка результатов и вывод общего статуса запросов
for idx, results in enumerate(all_results):
    success_count = sum(1 for result in results if result['status_code'] == 200)
    error_count = sum(1 for result in results if result['status_code'] != 200)
    total_time = sum(result['response_time'] for result in results)
    average_time = total_time / 100
    print(f"Results for {urls[idx]}:")
    print(f"Total Successful Requests: {success_count}")
    print(f"Total Failed Requests: {error_count}")
    print(f"Total Time for 100 Requests: {total_time} seconds")
    print(f"Average Response Time: {average_time} seconds\n")
