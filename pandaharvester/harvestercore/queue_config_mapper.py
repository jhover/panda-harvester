import os
import json
import datetime
import threading
from future.utils import iteritems


from pandaharvester.harvesterconfig import harvester_config
from .work_spec import WorkSpec
from .panda_queue_spec import PandaQueueSpec
from . import core_utils
from .db_proxy_pool import DBProxyPool as DBProxy


# class for queue config
class QueueConfig:

    def __init__(self, queue_name):
        self.queueName = queue_name
        # default parameters
        self.mapType = WorkSpec.MT_OneToOne
        self.useJobLateBinding = False
        self.zipPerMB = None
        self.siteName = ''
        self.maxWorkers = 0
        self.nNewWorkers = 0
        self.maxNewWorkersPerCycle = 0
        self.noHeartbeat = ''
        self.runMode = 'self'
        self.resourceType = PandaQueueSpec.RT_catchall
        self.getJobCriteria = None
        self.ddmEndpointIn = None
        self.allowJobMixture = False
        self.maxSubmissionAttempts = 3

    # get list of status without heartbeat
    def get_no_heartbeat_status(self):
        return self.noHeartbeat.split(',')

    # check if status without heartbeat
    def is_no_heartbeat_status(self, status):
        return status in self.get_no_heartbeat_status()


# mapper
class QueueConfigMapper:
    # constructor
    def __init__(self):
        self.lock = threading.Lock()
        self.lastUpdate = None

    # load data
    def load_data(self):
        with self.lock:
            # check interval
            timeNow = datetime.datetime.utcnow()
            if self.lastUpdate is not None and timeNow - self.lastUpdate < datetime.timedelta(minutes=10):
                return
            self.queueConfig = {}
            queueConfigJsonList = []
            # load config json on URL
            if core_utils.get_queues_config_url() is not None:
                dbProxy = DBProxy()
                queueConfigJson = dbProxy.get_cache('queues_config_file')
                if queueConfigJson is not None:
                    queueConfigJsonList.append(queueConfigJson.data)
            # define config file path
            if os.path.isabs(harvester_config.qconf.configFile):
                confFilePath = harvester_config.qconf.configFile
            else:
                # check if in PANDA_HOME
                confFilePath = None
                if 'PANDA_HOME' in os.environ:
                    confFilePath = os.path.join(os.environ['PANDA_HOME'],
                                                'etc/panda',
                                                harvester_config.qconf.configFile)
                    if not os.path.exists(confFilePath):
                        confFilePath = None
                # look into /etc/panda
                if confFilePath is None:
                    confFilePath = os.path.join('/etc/panda',
                                                harvester_config.qconf.configFile)
            # load config from local json file
            f = open(confFilePath)
            queueConfigJson = json.load(f)
            f.close()
            queueConfigJsonList.append(queueConfigJson)
            # set attributes
            for queueConfigJson in queueConfigJsonList:
                for queueName, queueDict in iteritems(queueConfigJson):
                    if queueName in self.queueConfig:
                        queueConfig = self.queueConfig[queueName]
                    else:
                        queueConfig = QueueConfig(queueName)
                    # queueName = siteName/resourceType
                    queueConfig.siteName = queueConfig.queueName.split('/')[0]
                    if queueConfig.siteName != queueConfig.queueName:
                        queueConfig.resourceType = queueConfig.queueName.split('/')[-1]
                    for key, val in iteritems(queueDict):
                        if isinstance(val, dict) and 'module' in val and 'name' in val:
                            if 'siteName' not in val:
                                val['siteName'] = queueConfig.siteName
                            if 'queueName' not in val:
                                val['queueName'] = queueConfig.queueName
                        setattr(queueConfig, key, val)
                    # additional criteria for getJob
                    if queueConfig.getJobCriteria is not None:
                        tmpCriteria = dict()
                        for tmpItem in queueConfig.getJobCriteria.split(','):
                            tmpKey, tmpVal = tmpItem.split('=')
                            tmpCriteria[tmpKey] = tmpVal
                        if len(tmpCriteria) == 0:
                            queueConfig.getJobCriteria = None
                        else:
                            queueConfig.getJobCriteria = tmpCriteria
                    # removal of some attributes based on mapType
                    if queueConfig.mapType == WorkSpec.MT_NoJob:
                        for attName in ['nQueueLimitJob']:
                            if hasattr(queueConfig, attName):
                                delattr(queueConfig, attName)
                    self.queueConfig[queueName] = queueConfig
            self.lastUpdate = datetime.datetime.utcnow()
        # update database
        dbProxy = DBProxy()
        dbProxy.fill_panda_queue_table(harvester_config.qconf.queueList, self)

    # check if valid queue
    def has_queue(self, queue_name):
        self.load_data()
        return queue_name in self.queueConfig

    # get queue config
    def get_queue(self, queue_name):
        self.load_data()
        if not self.has_queue(queue_name):
            return None
        return self.queueConfig[queue_name]

    # all queue configs
    def get_all_queues(self):
        self.load_data()
        return self.queueConfig
