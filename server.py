import socket
import os
import json
import time
import random
from protocol import criar_pacote, calcular_hash_arquivo, ler_pacote

SERVER_IP = '0.0.0.0'
SERVER_PORT = 2005
BUFFER_SIZE = 1022
TIMEOUT = 2
TAXA_DE_PERDA = 0.05
UPLOADS_DIR = os.path.join(os.path.dirname(__file__), 'uploads')
LOG_PATH = os.path.join(os.path.dirname(__file__), 'log_teste.txt')


def registrar_log(linha):
    with open(LOG_PATH, 'a') as log:
        log.write(f"{linha}\n")


def simular_perda_ativa(simular, contador):
    rand = random.random()
    if simular and rand < TAXA_DE_PERDA:
        print(f"[DEBUG - LOSS COUNT]: CONTADOR: {contador}")
        contador[0] += 1
        return True
    return False


def receber_upload(sock, addr, nome_arquivo, simular_perda):
    print(f"\n[UPLOAD] Iniciando recepco de '{nome_arquivo}' de {addr}")
    registrar_log(f"UPLOAD iniciado: {nome_arquivo} de {addr} | perda: {simular_perda}")
    SEQ_ESPERADO = 0
    caminho = os.path.join(UPLOADS_DIR, nome_arquivo)
    perda_count = [0]
    pacote_recebido = False

    with open(caminho, 'wb') as f:
        while True:
            pacote, _ = sock.recvfrom(1024)

            if not pacote_recebido:
                pacote_recebido = True
                if simular_perda:
                    print("[UPLOAD] Primeira perda forcada")
                    registrar_log("[UPLOAD] Primeira perda forcada")
                    continue

            if simular_perda_ativa(simular_perda, perda_count):
                print("[UPLOAD] Pacote descartado (simulado)")
                continue

            try:
                seq, tipo, dados = ler_pacote(pacote)
            except Exception as e:
                print(f"[UPLOAD] Pacote invalido descartado: {e}")
                continue

            print(f"[UPLOAD] Pacote recebido | Seq: {seq} | Tipo: {tipo} | Esperado: {SEQ_ESPERADO}")

            if tipo == 'F':
                print("[UPLOAD] Upload finalizado com sucesso.")
                break

            if seq == SEQ_ESPERADO:
                f.write(dados)
                ack = f"ACK{SEQ_ESPERADO}".encode()
                if simular_perda_ativa(simular_perda, perda_count):
                    print("[UPLOAD] ACK simulado como perdido")
                else:
                    sock.sendto(ack, addr)
                    print(f"[UPLOAD] ACK{SEQ_ESPERADO} enviado")
                SEQ_ESPERADO = 1 - SEQ_ESPERADO
            else:
                ack = f"ACK{1 - SEQ_ESPERADO}".encode()
                if simular_perda_ativa(simular_perda, perda_count):
                    print("[UPLOAD] ACK fora de ordem simulado como perdido")
                else:
                    sock.sendto(ack, addr)
                    print(f"[UPLOAD] ACK{1 - SEQ_ESPERADO} reenviado (fora de ordem)")

    registrar_log(f"UPLOAD finalizado | Pacotes perdidos (simulados): {perda_count[0]}")


def enviar_arquivo_com_acks(sock, addr, caminho_arquivo, simular_perda):
    SEQ = 0
    retransmissoes = 0
    tamanho_total_bytes = os.path.getsize(caminho_arquivo)
    perda_count = [0]

    print(f"\n[DOWNLOAD] Iniciando envio de '{caminho_arquivo}' para {addr}")
    registrar_log(f"DOWNLOAD iniciado: {caminho_arquivo} para {addr} | perda: {simular_perda}")
    print(f"[DOWNLOAD] Tamanho do arquivo: {tamanho_total_bytes} bytes")
    start = time.time()

    with open(caminho_arquivo, 'rb') as f:
        while True:
            chunk = f.read(BUFFER_SIZE)
            if not chunk:
                break

            enviado = False
            while not enviado:
                pacote = criar_pacote(SEQ, 'D', chunk)
                if simular_perda_ativa(simular_perda, perda_count):
                    pass
                else:
                    sock.sendto(pacote, addr)   

                sock.settimeout(TIMEOUT)
                try:
                    ack, _ = sock.recvfrom(1024)
                    if ack.startswith(f'ACK{SEQ}'.encode()):
                        SEQ = 1 - SEQ
                        enviado = True
                except socket.timeout:
                    retransmissoes += 1

    fim = criar_pacote(9, 'F', b'')
    sock.sendto(fim, addr)
    print("[DOWNLOAD] Pacote final enviado")

    end = time.time()
    tempo_total = end - start
    throughput = (tamanho_total_bytes * 8) / tempo_total

    print(f"[RESULTADO] Tempo total: {tempo_total:.2f} segundos")
    print(f"[RESULTADO] Throughput: {throughput / 1_000_000:.2f} Mbps")
    print(f"[RESULTADO] Pacotes retransmitidos: {retransmissoes}")

    registrar_log(f"DOWNLOAD finalizado | Retransmissoes: {retransmissoes} | Pacotes perdidos: {perda_count[0]} | Tempo: {tempo_total:.2f}s | Throughput: {throughput / 1_000_000:.2f} Mbps")

    # Envia o hash do arquivo
    hash_bytes = calcular_hash_arquivo(caminho_arquivo)
    hash_pacote = criar_pacote(10, 'H', hash_bytes)

    tentativas_hash = 0
    max_tentativas = 5
    ack_hash_recebido = False

    while tentativas_hash < max_tentativas and not ack_hash_recebido:
        sock.sendto(hash_pacote, addr)
        print(f"[HASH] Hash SHA-256 enviado (tentativa {tentativas_hash + 1})")
        registrar_log(f"[HASH] Hash SHA-256 enviado (tentativa {tentativas_hash + 1})")

        try:
            sock.settimeout(2)
            ack, _ = sock.recvfrom(1024)
            if ack == b"ACK_HASH":
                print("[HASH] ACK_HASH recebido do cliente")
                ack_hash_recebido = True
                break
        except socket.timeout:
            tentativas_hash += 1
            print("[HASH] Timeout aguardando ACK_HASH... reenviando")

    if not ack_hash_recebido:
        print("[HASH] Não recebeu ACK_HASH após múltiplas tentativas")
        registrar_log("[HASH] Falha ao confirmar recebimento do hash")

def start_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((SERVER_IP, SERVER_PORT))
    print(f"[SERVIDOR] Servidor UDP ativo em {SERVER_IP}:{SERVER_PORT}")

    if not os.path.exists(UPLOADS_DIR):
        os.makedirs(UPLOADS_DIR)
        print(f"[SERVIDOR] Diretório '{UPLOADS_DIR}' criado para armazenar uploads.")

    while True:
        try:
            data, addr = sock.recvfrom(1024)

            try:
                mensagem = data.decode().strip()
            except UnicodeDecodeError:
                print(f"[IGNORADO] Pacote binário recebido de {addr}. Ignorado no start_server.")
                continue

            simular_perda = ":SIMULAR_PERDA" in mensagem
            mensagem = mensagem.replace(":SIMULAR_PERDA", "")

            print(f"\n[REQ] De {addr} | Comando: {mensagem} | Perda simulada: {simular_perda}")
            registrar_log(f"Requisição de {addr}: {mensagem} | Perda: {simular_perda}")

            if mensagem == "LISTAR_ARQUIVOS":
                arquivos = os.listdir(UPLOADS_DIR)
                arquivos = [f for f in arquivos if os.path.isfile(os.path.join(UPLOADS_DIR, f))]
                resposta = json.dumps(arquivos).encode()
                perda_count = [0]
                if simular_perda_ativa(simular_perda, perda_count):
                    print("[LISTAGEM] Resposta descartada (simulado)")
                    registrar_log("[LISTAGEM] Resposta descartada (simulado)")
                else:
                    sock.sendto(resposta, addr)
                    print("[LISTAGEM] Lista de arquivos enviada")
                    registrar_log("[LISTAGEM] Lista enviada com sucesso")
                continue

            elif mensagem.startswith("UPLOAD:"):
                nome_arquivo = mensagem.split(":", 1)[1]
                receber_upload(sock, addr, nome_arquivo, simular_perda)
                continue

            elif mensagem.startswith("DOWNLOAD:"):
                nome_arquivo = mensagem.split(":", 1)[1]
                caminho_arquivo = os.path.join(UPLOADS_DIR, nome_arquivo)
                if not os.path.exists(caminho_arquivo):
                    print("[ERRO] Arquivo solicitado não encontrado")
                    sock.sendto(b'ARQUIVO_NAO_ENCONTRADO', addr)
                    continue
                enviar_arquivo_com_acks(sock, addr, caminho_arquivo, simular_perda)

        except KeyboardInterrupt:
            print("\n[SERVIDOR] Encerrado manualmente.")
            registrar_log("Servidor encerrado manualmente")
            break
        except socket.timeout:
            continue
        except Exception as e:
            print(f"[ERRO] {e}")
            registrar_log(f"[ERRO] {e}")

if __name__ == '__main__':
    start_server()
