from http import HTTPStatus
import logging
import os
import sys
import time

from dotenv import load_dotenv
import requests
from telegram import Bot

from exceptions import HTTPStatusNotOK


load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600

ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens():
    """Проверка токенов."""
    env_vars = [
        'PRACTICUM_TOKEN', 'TELEGRAM_TOKEN', 'TELEGRAM_CHAT_ID'
    ]
    invalid_env_vars = [var for var in env_vars if not globals().get(var)]
    message = f'Не валидные переменные окружения: {invalid_env_vars}'
    if invalid_env_vars:
        logging.critical(message)
        raise ValueError(message)
    return not invalid_env_vars


def send_message(bot, message):
    """Отправка сообщения бота в Telegram."""
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    logging.debug('Успешная отправка сообщения.')


def get_api_answer(timestamp):
    """Выполнение API-запроса."""
    params = {
        'url': ENDPOINT,
        'headers': HEADERS,
        'params': {'from_date': timestamp}
    }
    try:
        response = requests.get(**params)
    except requests.RequestException:
        raise Exception(
            f'Ошибка при подключении к странице {params.get("url")}'
        )

    response_code = response.status_code
    if response_code != HTTPStatus.OK:
        logging.error(
            f'Ошибка при загрузке страницы. {params}'
        )
        raise HTTPStatusNotOK(
            f'Страница загружена с ошибками! Код страницы {response_code}'
        )
    json = response.json()
    for key in ['error', 'code']:
        if key in json:
            logging.error(f'При загрузке страницы возникла ошибка {json[key]}')
            return
    return json


def check_response(response):
    """Проверка HTTP-ответа."""
    if not isinstance(response, dict):
        raise TypeError(
            f'Объект HTTP-ответа должен быть словарем, вместо {type(response)}'
        )
    if 'homeworks' not in response:
        raise KeyError('Ключ "homeworks" отсутсвует в словаре!')
    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        raise TypeError(
            f'Объект "homeworks" должен быть списком, вместо {type(homeworks)}'
        )
    return response


def parse_status(homework):
    """Получение статуса проверки домашнего задания."""
    status = homework['status']
    if 'homework_name' not in homework:
        raise KeyError('Ключ "homework_name" отсутсвует в словаре!')
    if status not in HOMEWORK_VERDICTS:
        raise ValueError(f'Неожиданное значение ключа "status" - {status}')
    verdict = HOMEWORK_VERDICTS[homework['status']]
    return ('Изменился статус проверки работы '
            f'"{homework["homework_name"]}". {verdict}')


def main():
    """Основная логика работы бота."""
    try:
        check_tokens()
    except Exception as error:
        logging.critical(f'Возникла ошибка: {error}')
        raise ValueError('Отсутствуют переменные окружения!')
    bot = Bot(token=TELEGRAM_TOKEN)

    timestamp = int(time.time())
    current_status = ''
    while True:
        try:
            response = get_api_answer(timestamp)
            timestamp = response['current_date']
            homeworks = check_response(response)['homeworks']
            if homeworks:
                status = homeworks[0]['status']
                if current_status != status:
                    verdict = parse_status(homeworks[0])
                    current_status = status
                    send_message(bot, verdict)
                else:
                    logging.debug('Статус проверки не изменился')
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logging.error(message, exc_info=True)
            send_message(bot, message)
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logger = logging.getLogger(__name__)
    logger.addHandler(
        logging.StreamHandler(stream=sys.stdout)
    )
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s, %(levelname)s, %(name)s, %(message)s',
        handlers=[logging.FileHandler(__file__ + '.log'),
                  logging.StreamHandler(sys.stdout)]
    )

    main()
