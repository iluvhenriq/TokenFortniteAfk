# TokenFortniteAfk

Um programa que joga Fortnite por você enquanto você está fora. Ele entra na partida, pula do ônibus, fica se mexendo e, quando você morre, volta pro lobby e começa de novo. Sem parar.

---

## 🐒 Passo a passo (siga na ordem, sem pular nada)

### Passo 1: Instalar o Python

1. Entre em https://www.python.org/downloads/
2. Clique no botão amarelo grande **Download Python**.
3. Abra o arquivo que baixou.
4. ⚠️ **MUITO IMPORTANTE:** lá embaixo da janela tem uma caixinha escrito **"Add Python to PATH"**. **MARQUE ELA.** Se não marcar, nada funciona.
5. Clique em **Install Now** e espere terminar.

### Passo 2: Instalar o VS Code

1. Entre em https://code.visualstudio.com/
2. Clique em **Download for Windows**.
3. Abra o arquivo que baixou e vá clicando em **Próximo** até acabar.

### Passo 3: Baixar este programa

1. Nesta página do GitHub, clique no botão verde **Code**.
2. Clique em **Download ZIP**.
3. Vá na pasta **Downloads**, clique com o botão direito no arquivo `.zip` e escolha **Extrair tudo**.
4. Agora você tem uma pasta chamada `TokenFortniteAfk-main`. Deixe ela num lugar fácil, tipo a Área de Trabalho.

### Passo 4: Abrir o VS Code COMO ADMINISTRADOR

⚠️ **Se não abrir como administrador, o jogo ignora o programa e nada acontece.**

1. Se o VS Code estiver aberto, feche.
2. Procure o ícone do **VS Code**, no menu Iniciar ou na Área de Trabalho.
3. Clique com o **botão DIREITO** nele.
4. Clique em **Executar como administrador**.
5. Se aparecer uma janela perguntando "Deseja permitir...?", clique em **Sim**.

### Passo 5: Abrir a pasta no VS Code

1. No VS Code, clique em **File** (ou **Arquivo**), lá no canto de cima à esquerda.
2. Clique em **Open Folder...** (ou **Abrir Pasta...**).
3. Escolha a pasta `TokenFortniteAfk-main` e clique em **Selecionar pasta**.
4. Se aparecer "Do you trust the authors?", clique em **Yes, I trust**.

### Passo 6: Abrir o terminal

1. Lá em cima, clique em **Terminal**.
2. Clique em **New Terminal** (ou **Novo Terminal**).
3. Vai aparecer uma caixa preta embaixo. Esse é o terminal, onde você vai digitar os comandos.

### Passo 7: Instalar o que falta (só na primeira vez)

Clique dentro da caixa preta, copie a linha abaixo, cole com **Ctrl+V** e aperte **Enter**:

```
pip install opencv-python numpy mss
```

Espere aparecer escrito **Successfully installed**. Pronto, isso nunca mais precisa ser feito.

### Passo 8: Abrir o programa

No mesmo terminal, copie isto, cole e aperte **Enter**:

```
python automacro.py
```

Vai abrir a janela do programa. 🎉

---

## 🎮 Como fazer ele jogar

1. Abra o Fortnite e deixe na tela do lobby, onde tem o botão **JOGAR**.
2. No jogo, aperte **F11**. Isso tira um print da tela.
3. Volte no programa, clique em **Recortar** do lado de "Botão JOGAR" e desenhe um quadrado em volta do botão JOGAR com o mouse.
4. Faça a mesma coisa com o **ônibus**: quando estiver dentro do ônibus, aperte **F11** e recorte algo que só aparece no ônibus.
5. Volte pro jogo e aperte **F6**. Ele começa a jogar sozinho.

**Pra parar:** aperte **F8**.

## ⌨️ Teclas

| Tecla | O que faz |
|---|---|
| **F6** | Liga / desliga |
| **F8** | 🛑 PARA TUDO (emergência) |
| **F11** | Tira print da tela |
| F7 | Salva a posição do mouse |
| F9 | Começa / para de gravar seus movimentos |
| F10 | Repete os movimentos gravados |

## 🔁 Da segunda vez em diante

Nem precisa do VS Code. Vá na pasta do programa, clique com o **botão DIREITO** no `iniciar.bat` e escolha **Executar como administrador**.

## 😵 Deu ruim?

| Problema | Solução |
|---|---|
| `python não é reconhecido` | Você não marcou "Add Python to PATH". Instale o Python de novo e marque a caixinha. |
| `pip não é reconhecido` | Mesmo problema de cima. |
| O programa abre, mas o jogo não se mexe | Você não abriu como administrador. Volte no Passo 4. |
| Ele não acha o botão JOGAR | Recorte o modelo de novo, com o quadrado bem em volta do botão. |

> ⚠️ Programas de AFK podem ser contra as regras da Epic Games. Se sua conta for banida, a culpa não é do programa. Use por sua conta e risco.

---

<details>
<summary>Coisas técnicas (pra quem entende)</summary>

| Arquivo | O que faz |
|---|---|
| `automacro.py` | Painel (tkinter), anti-AFK, cliques e atalhos globais via `RegisterHotKey` |
| `br_bot.py` | Bot de BR por template matching (OpenCV + mss) |
| `recorder.py` | Grava e reproduz rotas via Raw Input + SendInput |
| `automacro_config.json` | Configuração salva pelo painel |
| `modelos/` | Recortes usados no reconhecimento de tela |
| `rotas/` | Rotas gravadas |

`debug/`, `capturas/` e `log.txt` são gerados pelo programa e ficam fora do Git.
</details>
