import struct
import hashlib

def criar_pacote(seq, tipo, dados):
    """
    Cria um pacote com cabeçalho (seq, tipo) + dados
    """
    header = struct.pack('!BB', seq, ord(tipo))
    return header + dados

def ler_pacote(pacote):
    """
    Lê um pacote e retorna: (seq, tipo, dados)
    """
    seq, tipo = struct.unpack('!BB', pacote[:2])
    dados = pacote[2:]
    return seq, chr(tipo), dados

def calcular_hash_arquivo(path):
    sha256 = hashlib.sha256()
    with open(path, 'rb') as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    return sha256.digest()
