# TokenFortniteAfk

Painel para Windows que fica jogando partidas de Fortnite sozinho: anti-AFK, entra na fila, pula do ônibus, se mexe no chão e volta pro lobby quando o time morre. Tudo em loop.

## Arquivos

| Arquivo | O que faz |
|---|---|
| `automacro.py` | Painel principal (tkinter). Anti-AFK, cliques em pontos da tela e atalhos globais |
| `br_bot.py` | Bot de Battle Royale. Reconhece a tela por imagem (OpenCV) e faz o ciclo lobby → ônibus → queda → chão → sair |
| `recorder.py` | Grava e reproduz rotas de teclado e mouse (Raw Input + SendInput) |
| `iniciar.bat` | Abre o painel sem janela de console |
| `automacro_config.json` | Configurações salvas pelo painel |
| `modelos/` | Recortes de print usados pra reconhecer cada tela do jogo |
| `rotas/` | Rotas gravadas (`.json`) |

## Requisitos

- Windows 10 ou 11
- Python 3.10+ (com tkinter, que já vem no instalador oficial)
- Bibliotecas do bot:

```
pip install opencv-python numpy mss
```

O anti-AFK e o gravador de rotas usam só a biblioteca padrão. As bibliotecas acima só são necessárias para o `br_bot.py`.

## Como usar

1. Abra o painel com dois cliques no `iniciar.bat`, ou rode `python automacro.py`.
2. Deixe o Fortnite em janela ou em tela cheia sem bordas.
3. **Modelos:** no jogo, aperte **F11** na tela certa pra tirar um print. Depois, no painel, selecione o modelo e clique em **Recortar** pra arrastar um retângulo em volta do elemento. Os modelos obrigatórios são o botão **JOGAR** e o **ônibus**. Os outros são opcionais e deixam o bot mais confiável.
4. Aperte **F6** pra iniciar.

## Atalhos

| Tecla | Ação |
|---|---|
| F6 | Iniciar / parar o macro |
| F7 | Capturar a posição do mouse pro ponto selecionado |
| F8 | Parada de emergência |
| F9 | Gravar / parar gravação de rota |
| F10 | Reproduzir / parar a rota selecionada |
| F11 | Tirar print da tela (pra recortar modelos) |

## Observações

- O macro só age com a janela do Fortnite em foco (opção `only_when_focused`).
- Os prints de debug vão pra `debug/`, os prints do F11 vão pra `capturas/`, e o log fica em `log.txt`. Nenhum deles vai pro Git.
- Macros e bots de AFK podem violar os termos de uso da Epic Games. Use por sua conta e risco.
