import socket
import os
from protocol import criar_pacote, calcular_hash_arquivo, ler_pacote

SERVER_IP = '0.0.0.0'
SERVER_PORT = 2005
BUFFER_SIZE = 1022  # 1024 - 2 bytes de header
TIMEOUT = 2

def receber_upload(sock, addr, nome_arquivo):
    print(f"Recebendo upload de {nome_arquivo} de {addr}")
    SEQ_ESPERADO = 0
    caminho = os.path.join('uploads', nome_arquivo)

    with open(caminho, 'wb') as f:
        while True:
            pacote, _ = sock.recvfrom(1024)
            seq, tipo, dados = ler_pacote(pacote)

            if tipo == 'F':
                print("Upload finalizado.")
                break

            if seq == SEQ_ESPERADO:
                f.write(dados)
                ack = f"ACK{SEQ_ESPERADO}".encode()
                sock.sendto(ack, addr)
                SEQ_ESPERADO = 1 - SEQ_ESPERADO
            else:
                ack = f"ACK{1 - SEQ_ESPERADO}".encode()
                sock.sendto(ack, addr)

def enviar_arquivo_com_acks(sock, addr, caminho_arquivo):
    SEQ = 0
    with open(caminho_arquivo, 'rb') as f:
        while True:
            chunk = f.read(BUFFER_SIZE)
            if not chunk:
                break

            enviado = False
            while not enviado:
                pacote = criar_pacote(SEQ, 'D', chunk)
                sock.sendto(pacote, addr)
                sock.settimeout(TIMEOUT)

                try:
                    ack, _ = sock.recvfrom(1024)
                    if ack.startswith(f'ACK{SEQ}'.encode()):
                        print(f"ACK {SEQ} recebido.")
                        SEQ = 1 - SEQ
                        enviado = True
                except socket.timeout:
                    print(f"Timeout! Reenviando pacote {SEQ}.")

    # Pacote de fim
    fim = criar_pacote(9, 'F', b'')
    sock.sendto(fim, addr)
    print("Transferência finalizada.")

    # Enviar hash SHA-256
    hash_bytes = calcular_hash_arquivo(nome_arquivo)
    hash_pacote = criar_pacote(10, 'H', hash_bytes)
    sock.sendto(hash_pacote, addr)
    print("Hash SHA-256 enviado.")

def start_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((SERVER_IP, SERVER_PORT))
    print(f"Servidor UDP ouvindo em {SERVER_IP}:{SERVER_PORT}")

    while True:
        try:
            data, addr = sock.recvfrom(1024)
            mensagem = data.decode()

            # Verifica se é upload
            if mensagem.startswith("UPLOAD:"):
                nome_arquivo = mensagem.split(":", 1)[1]
                print(f"Requisição de UPLOAD de {addr}: {nome_arquivo}")
                receber_upload(sock, addr, nome_arquivo)
                continue

            # Caso contrário, assume que é download
            nome_arquivo = mensagem
            print(f"Requisição de DOWNLOAD de {addr}: {nome_arquivo}")

            UPLOADS_DIR = os.path.join(os.path.dirname(__file__), 'uploads')

            caminho_arquivo = os.path.join(UPLOADS_DIR, nome_arquivo)

            if not os.path.exists(caminho_arquivo):
                sock.sendto(b'ARQUIVO_NAO_ENCONTRADO', addr)
                continue

            enviar_arquivo_com_acks(sock, addr, caminho_arquivo)

        except KeyboardInterrupt:
            print("\nServidor encerrado manualmente.")
            break
        except ConnectionResetError:
            print("[INFO] Cliente fechou a conexão (WinError 10054)")
            continue
        except socket.timeout:
            print("[INFO] Timeout de recepção, aguardando nova requisição...")
            continue
        except Exception as e:
            print(f"[ERRO NO SERVIDOR] {e}")


if __name__ == '__main__':
    start_server()
