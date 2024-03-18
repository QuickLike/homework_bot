from http import HTTPStatus
import logging
import os
import requests
import sys
import time

from dotenv import load_dotenv
from telegram import Bot

from exceptions import (
    HTTPStatusNotOK, MessageSendingError, ResponseContentError, StatusError
)


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
    return (PRACTICUM_TOKEN or TELEGRAM_TOKEN or TELEGRAM_CHAT_ID)


def send_message(bot, message):
    """Отправка сообщения бота в Telegram."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except MessageSendingError as error:
        raise MessageSendingError(f'Сбой при отправке сообщения. {error}')
    else:
        logging.debug('Успешная отправка сообщения.')


def get_api_answer(timestamp):
    """Выполнение API-запроса."""
    try:
        response = requests.get(
            url=ENDPOINT,
            headers=HEADERS,
            params={'from_date': timestamp}
        )
        response_code = response.status_code
        if response_code != HTTPStatus.OK:
            raise HTTPStatusNotOK(
                f'Страница загружена с ошибками! Код страницы {response_code}'
            )
        return response.json()
    except requests.RequestException as error:
        logging.error(error, exc_info=True)


def check_response(response):
    """Проверка HTTP-ответа."""
    if not isinstance(response, dict):
        raise TypeError('Объект HTTP-ответа должен быть словарем!')
    if 'homeworks' not in response:
        raise ResponseContentError('Ключ "homeworks" отсутсвует в словаре!')
    if 'current_date' not in response:
        raise ResponseContentError('Ключ "current_date" отсутсвует в словаре!')
    if not isinstance(response['homeworks'], list):
        raise TypeError('Объект "homeworks" должен быть списком!')
    return response


def parse_status(homework):
    """Получение статуса проверки домашнего задания."""
    status = homework['status']
    if 'homework_name' not in homework:
        raise KeyError('Ключ "homework_name" отсутсвует в словаре!')
    if status not in HOMEWORK_VERDICTS or not status:
        raise StatusError('Ошибка статуса')
    verdict = HOMEWORK_VERDICTS[homework['status']]
    return ('Изменился статус проверки работы '
            f'"{homework["homework_name"]}". {verdict}')


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        logging.critical('Отсутствуют переменные окружения!')
        sys.exit('Остановка программы')
    bot = Bot(token=TELEGRAM_TOKEN)

    timestamp = int(time.time())
    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)['homeworks']
            if homeworks:
                homework = parse_status(homeworks[0])
                send_message(bot, homework)
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
        format='%(asctime)s, %(levelname)s, %(message)s, %(name)s'
    )

    main()
