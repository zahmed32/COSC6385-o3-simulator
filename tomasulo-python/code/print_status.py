# Qing 
# 21st May 2017

# function: print RS/ROB status
def ps(unit):
    if(len(unit)==0):
        print('empty!')
    else:
        # get all fields in namedtuple
        fields_list = vars(unit[0])
        for unit_item in unit:
            print ('******')
            for field in fields_list:
                print(field+': ', str(getattr(unit_item, field)))

# function: print single namedtuple
def pss(snt):
    fields_list = vars(snt)
    for field in fields_list:
        print (field+': ', str(getattr(snt, field)))

