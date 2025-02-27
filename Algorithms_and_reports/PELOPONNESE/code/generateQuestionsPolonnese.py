import pygsheets
import pandas as pd
import numpy as np
import random
import openpyxl
from sklearn.cluster import KMeans


class Cache_operations:
    # singleton instance
    __instance = None

    # local file configurations
    google_key_file, question_levels = './keyGoogleSheet.json', "./question_level.xlsx"
    data_sheet_question, data_sheet_answer = 'Data_input', 'partner_output_peloponnese'

    # cache information to prevent redundant requests
    data_cache = None
    cache_questions = pd.DataFrame()
    cache_answer = pd.DataFrame()
    count = 250

    # blocking the init method to avoid incorrect usage of singleton class
    def __init__(self):
        raise Exception("Singleton Class! use get_instance()")

    # permite instanciate this class using the singleton pattern
    @classmethod
    def get_instance(cls):
        if not cls.__instance:
            cls.__instance = cls.__new__(cls)
        return cls.__instance

    # the initial load with 'initial' configurations.
    # this configs can be reloaded separately if needed
    def load(self):
        self.get_questions()

    # get authorization for access the spreadsheet
    def __get_google_authorization(self):
        return pygsheets.authorize(service_file=self.google_key_file)

    # google 'open(file)' for the spreadsheet
    def get_data(self):
        ga = self.__get_google_authorization()
        self.data_cache = ga.open_by_key('1ShUilbDAzeq2XgP9ALpVX2jTjYU9NBDB_CNj0qsg4Uo')
        return self.data_cache

    # get the questions from google sheets and merge with the local file of levels
    # return dataframe with [question, answer, level]
    def get_questions(self, update=False):
        self.count -= 1
        count_extouro = self.count == 0
        self.create_table()
        if self.cache_questions.shape[0] == 0 or update or count_extouro:
            self.count=250
            self.get_data()
            questions = self.data_cache.worksheet_by_title(self.data_sheet_question)
            questions = questions.get_as_df(has_header=True)
            questions = questions[['id_prototype', 'correct answer']].copy().head(40)
            questions.columns = ['id', 'answer']
            levels = pd.read_excel(self.question_levels)
            questions = questions.merge(levels, left_on="id", right_on="question")
            questions = questions.drop("question", axis=1)
            self.cache_questions = questions
        return self.cache_questions.copy()

    def create_table(self):
        self.get_data()
        questions = self.data_cache.worksheet_by_title(self.data_sheet_question)
        questions = questions.get_as_df(has_header=True)
        questions = questions[['id_prototype', 'correct answer']].dropna()

        graph_dataset = pd.read_excel('keys.xlsx')
        graph_dataset['key'] = graph_dataset.drop(['ID', 'level'], axis=1).apply(lambda x: (x[x == 1]).index.values,
                                                                                 axis=1)
        graph_dataset = graph_dataset.explode('key').reset_index()[['ID', 'key', 'level']]
        graph = graph_dataset.merge(questions, left_on="ID", right_on="id_prototype").drop('id_prototype', axis=1)
        return graph


    # get all the answers of a given sheet, transfrom and process the data,
    # returning a dataframe with [email, id, test, correct ] where:
    #   - id is the question id
    #   - test is a simple separator of each row in the original sheet
    #   - correct is integer ( 0 if wrong or 1 if correct )
    def get_answers(self, update=False):
        if self.cache_answer.shape[0] == 0 or update:
            self.get_data()
            answer = self.data_cache.worksheet_by_title(self.data_sheet_answer)
            answer = answer.get_as_df(has_header=False)
            result = pd.DataFrame()
            for quest in range(8, 17, 2):
                ans = quest + 1
                temp = pd.DataFrame()
                temp['email'] = answer[3]
                temp['question'] = answer[quest]
                temp['answer'] = answer[ans]
                temp['test'] = answer.index
                temp['order'] = (quest - 6) / 2
                result = pd.concat([result, temp])
            answer = result
            
            quest = self.get_questions().rename(columns={"answer": "correct_ans"})
            answer = answer.tail(-1)
            answer = answer.merge(quest, left_on='question', right_on="id")
            answer['correct'] = (answer["answer"] == answer["correct_ans"]).apply(lambda x: int(x))
            answer = answer[['email', 'test', 'question', 'correct', 'order']]
            answer = answer.dropna(subset=["question"]).sort_values(['test', 'order'])
            answer = answer.reset_index().drop(['index', 'order'], axis=1)
            global df_clustering_level
            df_clustering_level = answer
            self.cache_answer = answer
        return self.cache_answer.copy()

    def clustering_level(self, email):
        global  df_clustering_level
        kmeans = KMeans(n_clusters=5)
        df_clustering_level['AvarageScore'] = df_clustering_level.groupby('email')['correct'].transform('mean')
        X = df_clustering_level[['AvarageScore']]
        kmeans.fit(X)
        df_clustering_level['cluster'] = kmeans.labels_
        df_clustering_level['cluster'] = df_clustering_level['cluster'] + 1
        print(df_clustering_level)
        user_level_question = df_clustering_level[df_clustering_level['email'] == email]
        
        if user_level_question.empty:
            return 1
        else:
            user_level_question = user_level_question['cluster'].iloc[-1]
            return user_level_question

cache = Cache_operations.get_instance()

# receives the information from plataform
# return the user email and a sheet with:
#   question id column as "question" <int>
#   correct answer as "correct" <int 0/1>
# keep just the 'answered questions' in each row
def format_current_data(current_data):
    email, sheet = "", pd.DataFrame()
    email = current_data[3]
    values = [[current_data[i], current_data[i + 1]] for i in range(8, 18, 2)]
    values = list(filter(lambda x: x[0] != '-1', values))
    sheet = pd.DataFrame(values, columns=['question', 'choose'])
    sheet = sheet.merge(cache.get_questions(), left_on='question', right_on='id')
    sheet['answer'] = sheet['answer'].astype(float)
    sheet['choose'] = sheet['choose'].astype(float)
    sheet['correct'] = (sheet['choose'] == sheet["answer"]).apply(lambda x: int(x))
    sheet = sheet[["id", "correct", "choose"]]
    return email, sheet

# receives the user email and return a filtered
# sheet with the columns:
#   question id colum as "id" <int>
#   correct answer as "correct" <int 0/1>
def get_user_history(user_email):
    ans = cache.get_answers()
    history = ans[ans["email"] == user_email]
    return history[['question', 'correct']].copy()

# receives the user current data and the user history
# returns a sheet ([0,1] rows) with the last question answered:
#   question id column as "question"
#   correct answer as "correct"
# if the user never used the plataform, will return blank sheet
# ignore all skiped questions
def get_last_question(current_data, user_history):
    if user_history.shape[0] > 0:
        user_history = user_history.copy()
        user_history = user_history.rename(columns={'question': 'id'})
        user_history["choose"] = "<last test>"
    temp = pd.concat([user_history, current_data])
    if temp.shape[0] > 0: temp = temp[temp["choose"].notnull()]
    return temp.tail(1)

# receives the last question of the user and follow the steps:
# - get the level of the last question
# - check if the user answer correctly
#     - if correct: user level = question level + 1
#     - if wrong or I don't know : user level = question level - 1
# available levels are : 1,2,3,4,5
# OBS: the last question is the ''
def get_user_level(sheet_last_question):
    user_level = 0
    if sheet_last_question.shape[0] > 0:
        question_id = sheet_last_question["id"].values[0]
        is_correct = sheet_last_question["correct"].values[0]
        questions = cache.get_questions()
        questions = questions[questions['id'] == question_id]
        user_level = questions["level"].values[0]
        point = 1 if is_correct else -1
        user_level += point
    return max(1, min(5, user_level))

# function to check if is the requisition for the first question
# this functions is helps to controll the 'answer data' in cache
def is_first_question(current_data):
    return current_data.shape[0] == 0

# function to "debbug" with simple messages
def debugg_function(email, level, hist, next):
    lst = hist.tail(1)
    if lst.shape[0] == 0:
        print(f"email: {email} | level: {level} | last quest: -- | correct: - | next: {next}")
    else:
        print(
            f"email: {email} | level: {level} | last quest: {lst['id'].values[0]:2d} | correct: {lst['correct'].values[0]} | next: {next}")

def next_question_choose(level, historic, current_data, plattaform_user_action):
    #In case of reaching the maximum level and getting it right, in the future an image of congratulations
    if level == 6: return -1
    
    questions = cache.get_questions()
    historic['correct'] = historic['correct'].astype(int)
    already_correct = list(historic[historic['correct'] == 1]["id"].unique())
    all_questions_answered = list(set(already_correct + list(current_data['id'])))

    #graph: is the table of questions with their keywords, level, correct answer and correct answers 
    graph = cache.create_table()
    graph_level = graph[ graph['level'] == level ]
    teste= graph_level['ID'].unique()

    graph_level = graph_level[graph_level['ID'].apply(lambda x: not x in all_questions_answered)]
    
    #When the cluster questions are finished, it returns the questions
    if graph_level.shape[0] == 0 : return next_question_choose(level + 1, historic, current_data, plattaform_user_action)  # magic recursion
    
    list_questions = graph_level['ID'].unique()

    next_question = random.choice(list_questions)

    return next_question


# receives a parameter for the plataform execute all the steps and function calls
# return a number <int> with the choosen question id (next question to be answered)
def entrypoint(plattaform_user_action):
    email, current_data = format_current_data(plattaform_user_action)
    if is_first_question(current_data): cache.get_answers(update=True)
    user_history = get_user_history(email)
    last_answer = get_last_question(current_data, user_history)
    user_question_level = cache.clustering_level(email) if is_first_question(current_data) else get_user_level(last_answer)
    #user_question_level = get_user_level(last_answer)
    if current_data.shape[0] > 0:
        if user_question_level != 1:
            user_question_level = user_question_level + 1 if current_data['choose'].tail(1).iloc[0] == 4 else user_question_level
            user_question_level = max(1, min(5, user_question_level))
    user_full_hist = pd.concat([user_history.rename(columns={'question': 'id'}), current_data])
    user_full_hist = user_full_hist.drop("choose", axis=1)
    next_question = next_question_choose(user_question_level, user_full_hist, current_data, plattaform_user_action)
    debugg_function(email, user_question_level, user_full_hist, next_question)
    return next_question
