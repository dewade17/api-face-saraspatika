# logger_config.py

import logging

def setup_logger():
    # Membuat logger khusus untuk worker
    logger = logging.getLogger('worker_logger')
    logger.setLevel(logging.INFO) # Atur level minimum ke INFO

    # Mencegah logger mengirim output ke console lebih dari sekali
    if logger.hasHandlers():
        logger.handlers.clear()

    # Membuat file handler untuk menulis log ke file 'worker.log'
    # 'a' berarti append, log baru akan ditambahkan di bawah log lama
    file_handler = logging.FileHandler('worker.log', mode='a')

    # Membuat format log agar lebih mudah dibaca
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(module)s - %(funcName)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)

    # Menambahkan file handler ke logger
    logger.addHandler(file_handler)

    return logger

# Buat satu instance logger untuk digunakan di seluruh aplikasi
log = setup_logger()