from flask import Flask, render_template, request, send_file, flash, redirect
from flask_paginate import Pagination, get_page_args

import os
import requests
import html

from tempfile import TemporaryFile
import xml.etree.ElementTree as ET
import re

# SITE = "http://localhost:8983"
SITE = os.environ.get("SOLR_SITE")

MSG_SOLR_OFFLINE = "Solr está fora do ar."
MSG_ERROR_DOWNLOAD = "Não foi possível fazer download."
MSG_ERROR_CORE = "Não foi possível encontrar o Banco de Questões selecionado."

options = [
    ('selected value=',   'Banco de Questões'),
    ('value=enem2020',    'Enem 2020'),
    ('value=enem2019',    'Enem 2019'),
    ('value=enem2018',    'Enem 2018'),
    ('value=enem2017',    'Enem 2017'),
    ('value=enem2016',    'Enem 2016'),
    ('value=enem2016-p2', 'Enem 2016 - Segunda Aplicação'),
    ('value=enem2015',    'Enem 2015'),
    ('value=enem2015-p2', 'Enem 2015 - Segunda Aplicação'),
    ('value=enem2014',    'Enem 2014'),
    ('value=enem2014-p2', 'Enem 2014 - Segunda Aplicação'),
    ('value=enem2013',    'Enem 2013'),
    ('value=enem2013-p2', 'Enem 2013 - Segunda Aplicação'),
    ('value=enem2012',    'Enem 2012'),
    ('value=enem2012-p2', 'Enem 2012 - Segunda Aplicação'),
    ('value=enem2011',    'Enem 2011'),
    ('value=enem2011-p2', 'Enem 2011 - Segunda Aplicação'),
    ('value=enem2010',    'Enem 2010'),
    ('value=enem2009',    'Enem 2009'),
    ('value=outros',      'Outros'),
]

app = Flask(__name__)
# app.config['SECRET_KEY'] = '000000000000'
app.config['SECRET_KEY'] = os.environ.get("SOLR_FLASK_SECRET_KEY")


@app.route('/', methods=["GET", "POST"])
def index():
    return render_template("index.html", options=options)


@app.route('/search', methods=["GET", "POST"])
def search():
    page, per_page, offset = get_page_args(page_parameter='page', per_page_parameter='per_page')
    per_page = 5
    offset = (page-1)*per_page
    # print(f'page: {page}\nper_page: {per_page}\noffset: {offset}')

    query = str(request.args.get("query"))
    if(not query):
        # Se o campo de busca for enviado em branco
        query = "*:*"

    core = str(request.args.get("core"))
    # print(f'core: {core}')

    try:
        response = requests.get(
            f"{SITE}/solr/{core}/select?indent=true&q.op=OR&q={query}&rows={per_page}&start={offset}"
        )
        # print(f"response code: {response.status_code}")
    except requests.ConnectionError:
        # Solr offline
        flash(MSG_SOLR_OFFLINE)
        return render_template("index.html")

    if(response.status_code == 404):
        # Core não encontrado no Solr
        flash(MSG_ERROR_CORE)
        return redirect(request.referrer)

    message = response.json()
    # print(message)

    status = message['responseHeader']['status']
    if(status != 0 ):
        # Algum erro de query do Solr
        flash(message['error']['msg'])
        return redirect(request.referrer)

    total = message['response']['numFound']
    questions = message['response']['docs']
    if total > 0:
        for question in questions:
            to_pop = ['_version_', 'texto_completo']
            for field in to_pop:
                question.pop(field, None)

            # Retita conteúdos de [lista]
            for i in question:
                if(len(question[i]) == 1):
                    question[i] = question[i][0]

    pagination = Pagination(page=page, per_page=per_page, total=total, css_framework='bootstrap5')

    return render_template("search.html",
                           core=core,
                           query=query,
                           questions=questions,
                           page=page,
                           per_page=per_page,
                           pagination=pagination,
                           total=total,
                           options=options,
                           )


@app.route('/downlaod', methods=["GET", "POST"])
def download_file():
    core = str(request.args.get("core"))
    doc_id = str(request.args.get("doc_id"))
    format = str(request.args.get("format")) # formato de download (moodle, classroom, ...)

    query = f"id:{doc_id}"

    try:
        response = requests.get(f"{SITE}/solr/{core}/select?indent=true&q.op=OR&q={query}")
    except requests.ConnectionError:
        flash(MSG_SOLR_OFFLINE)
        return render_template("index.html")

    message = response.json()

    # print("Download page")
    # print(f"core: {core}")
    # print(f"doc_id: {doc_id}")
    # print(f"format: {format}")
    # print(f"message: {message}")

    status = message['responseHeader']['status']
    if(status != 0):
        # Erro do Solr
        flash(message['error']['msg'])
        return redirect(request.referrer)

    total = message['response']['numFound']
    questions = message['response']['docs'][0]
    if total == 0:
        flash(MSG_ERROR_DOWNLOAD)
        return redirect(request.referrer)
    else:
        gabarito = questions.pop("gabarito", [None])[0]
        enunciado = questions.pop("enunciado", [None])[0]

    # print(f"questions: {questions}")
    # print(f"gabarito: {gabarito}")
    # print(f"enunciado: {enunciado}")

    data = ET.Element('quiz')

    question = ET.SubElement(data, 'question')
    question.set('type', 'multichoice')

    name = ET.SubElement(question, 'name')
    name_text = ET.SubElement(name, 'text')
    name_text.text = questions.pop("numero", [None])[0]

    questiontext = ET.SubElement(question, 'questiontext')
    questiontext.set('format', 'moodle_auto_format')
    questiontext_text = ET.SubElement(questiontext, 'text')
    questiontext_text.text = enunciado

    shuffleanswers = ET.SubElement(question, 'shuffleanswers')
    shuffleanswers.text = "false"
    answernumbering = ET.SubElement(question, 'answernumbering')
    answernumbering.text = "ABCD"

    frac_ans = {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'E': 0, gabarito: 100}

    for i in frac_ans:
        answer = ET.SubElement(question, 'answer')
        answer.set('fraction', str(frac_ans[i]))
        answer_text = ET.SubElement(answer, 'text')
        answer_text.text = questions.pop(i.lower(), [None])[0]

    # Converting the xml data to byte object, for allowing flushing data to file stream
    b_xml = ET.tostring(data, encoding='UTF-8', xml_declaration=True)

    file = TemporaryFile("w+b")
    file.write(b_xml)
    file.seek(0)
    return send_file(file, as_attachment=True, download_name=f"DB_{doc_id}.xml")


if __name__ == '__main__':
    app.run(debug=True)

    # core = "enunciados_simples"
    # query = "enunciado:vegetais"
    # response = requests.get(f"{SITE}/solr/{core}/select?indent=true&q.op=OR&q={query}")
    # mesage = response.json()
    # print(mesage['response']['numFound'])
    # print(mesage['response']['docs'])
    # for question in mesage['response']['docs']:
    #     for field in question:
    #         if(field not in ['id', '_version_']):
    #             print(f"{field}: {question[field][0]}")
