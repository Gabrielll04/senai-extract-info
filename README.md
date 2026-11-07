# Extração de deslocamentos de viagem → planilha de GEE

O script lê os PDFs digitalizados de prestação de contas de viagem (relatório SAP *"Cálculo de despesas/comprovante de despesas de viagem"* e os anexos). Com OCR, ele identifica os deslocamentos de **carro próprio** e de **Uber** e lança a distância percorrida na planilha do modelo `modelo/modelo_planilha.xlsx`.

## O que é extraído

| Coluna da planilha | Origem no PDF |
|---|---|
| A – Registro da frota | `PLACA` se houver trajetos de carro na seção **Trajeto** do relatório; `UBER` se houver recibos Uber anexados. Se houver os dois, são **duas linhas**. |
| B – Evidência | Número da **Viagem** (`Viagem: 2111002329`) |
| C – Descrição do passageiro | Número abaixo do nome do colaborador, no topo da 1ª página. É conferido com o `Nº pessoal` das páginas seguintes. |
| D / E – Tipo / Ano da frota | **PLACA:** vazios. **UBER:** `Automóvel flex a gasolina` / `2016` (valores do modelo; o recibo não informa o veículo). Para mudar, use `--uber-tipo-frota` e `--uber-ano-frota`. |
| F…Q – jan…dez | **PLACA:** soma do `Trajeto total (km)` de cada trajeto, no mês da data do trajeto. **UBER:** soma dos `Quilômetros` de cada recibo, no mês da **data do recibo**. |
| R – Observações | Avisos para conferência manual (veja abaixo) |

As distâncias de carro e de Uber **nunca são somadas entre si**. Se as corridas ou os trajetos de um documento caírem em meses diferentes, cada mês recebe só o que foi feito nele.

## Dupla confirmação dos km de carro

No relatório, o km de cada trajeto aparece duas vezes: em "Trajeto total (km)" e em "km/mi.". Um valor só é lançado quando **pelo menos duas leituras concordam e são maioria**.

- Se não houver esse consenso, o script relê a página com outras configurações de OCR (outra resolução e outro modo de leitura) e vota de novo.
- Se mesmo assim não houver consenso, o trajeto **não é lançado**, e o aviso mostra os valores lidos para conferência.

Assim, um dígito lido errado (225 lido como 228, por exemplo) não entra na planilha sem que ninguém perceba.

## Conferências automáticas

Quando algo não fecha, o script **não chuta valores**. Ele escreve um aviso na coluna *Observações* e no relatório de conferência:

- um "Trajeto total" que não pôde ser lido, ou que diverge do `km/mi.` do mesmo trajeto;
- nº da viagem ou nº pessoal ilegível, ou divergente entre as páginas;
- recibo Uber sem data ou km legível (antes de desistir, o script tenta de novo com outro modo de OCR);
- soma dos valores dos recibos Uber diferente do lançamento de **Táxi** no relatório (sinal de recibo faltando);
- página que parece recibo de corrida, mas não é Uber (por exemplo, 99 ou táxi comum);
- trajetos ou corridas em anos diferentes.

Cada execução gera também o arquivo `conferencia_<planilha>_<data>.csv`, ao lado da planilha. Ele lista cada trajeto e cada corrida lidos (data, km, valor, página do PDF) e todos os avisos.

## Planilha incremental

- Se a planilha de saída não existir, ela é criada a partir do modelo.
- Se existir, as novas linhas são acrescentadas no final.
- Um documento que já foi lançado (mesmo tipo + mesma evidência) é **ignorado**, para não duplicar.
- Para regravar documentos já lançados (por exemplo, depois de corrigir um problema), use `--substituir`. A linha existente é sobrescrita no mesmo lugar.
- Feche a planilha no Excel antes de rodar o script.

## Instalação (Windows)

1. **Python 3.10 ou mais novo:** https://www.python.org/downloads/
2. **Tesseract OCR:** instale pelo instalador da UB Mannheim (https://github.com/UB-Mannheim/tesseract/wiki). Na tela *"Additional language data"*, marque **Portuguese**. Deixe a pasta de instalação padrão: o script encontra o Tesseract lá sozinho.
3. **Dependências do Python:** dê dois cliques em **`instalar.bat`**. Se preferir, rode no Prompt de Comando, dentro da pasta do projeto:
   ```bash
   py -m pip install -r requirements.txt
   ```

Use `py -m pip`, e não só `pip`: no Windows, o comando `pip` sozinho costuma não estar no PATH.

Se o Tesseract foi instalado em outra pasta, informe a **pasta** de instalação (ou o caminho do `tesseract.exe`) com `--tesseract "D:\...\Tesseract-OCR"`. O script já procura sozinho em `C:\Program Files\Tesseract-OCR` e em `%LOCALAPPDATA%\Tesseract-OCR`.

No Linux, use `sudo apt install tesseract-ocr tesseract-ocr-por` e depois `pip install -r requirements.txt`.

## Uso

```bash
py extrair_viagens.py "C:\Users\Aluno\Desktop\viagens"
```

Sem a opção `-o`, a planilha é criada (ou atualizada) como `planilha_GEE.xlsx` **dentro da pasta dos PDFs**. Para escolher outro arquivo, use `-o`:

```bash
py extrair_viagens.py "C:\Users\Aluno\Desktop\viagens" -o "C:\Users\Aluno\Desktop\planilha_GEE_2026.xlsx"
```

Se algum documento for lido de forma estranha, rode de novo com `--salvar-texto "C:\...\texto_ocr"`. O script grava o texto que o OCR leu de cada PDF, o que ajuda a diagnosticar o problema.

Também dá para passar arquivos PDF avulsos, ou várias pastas. Cada documento leva cerca de 1 minuto (são cerca de 2 s por página).

## IA com visão (próxima etapa)

O OCR é o caminho principal. O arquivo `extrator/visao.py` já define o ponto em que uma IA com visão entra: ela é chamada **só** nas páginas que o OCR não conseguiu ler com segurança. Depois de escolher o provedor, basta implementar `ExtratorVisao` e rodar com `--visao <provedor>`.

## Testes

```bash
python -m unittest discover -s tests -t .
```

Os testes usam textos fictícios. **Não** coloque PDFs reais no repositório: eles contêm dados pessoais (o `.gitignore` já bloqueia `*.pdf`).
