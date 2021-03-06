#!/usr/bin/env python

# -*- coding: utf-8 -*-

"""
Created on Thu Sep  5 10:09:21 2019
@author: Matan Samina
"""
import rospy
import numpy as np
from rospy_tutorials.msg import Floats # for landmarks array
from rospy.numpy_msg import numpy_msg # for landmarks array 
import matplotlib.pyplot as plt
from sklearn.neighbors import NearestNeighbors # for KNN algorithm
from geometry_msgs.msg import Transform # for transpose of map
import operator
from scipy.optimize import differential_evolution
import copy
import pandas as pd
import os
from joblib import Parallel, delayed
import multiprocessing
from sklearn.cluster import KMeans
from sklearn.mixture import BayesianGaussianMixture
# ground_trouth_origin = np.array([-14.0, 0, 0.0]) #map1
# ground_trouth_target = np.array([-2.8, 5, -1.57]) #map1

ground_trouth_origin = np.array([-12,-5.0, 0]) #map3
ground_trouth_target = np.array([4.0, -8.0, -2.75]) #map3

num_cores = multiprocessing.cpu_count()
import rospkg
class tPF():
    
    def __init__(self):

        self.pub = rospy.Publisher('/TM2', Transform , queue_size=1000 )
        rospy.init_node('listener', anonymous=True)
       
        # creat first particales 
       

        # convert maps to landmarks arrays:
        self.oMap = maps("LM1")
        self.anti_oMap = maps("LM1_anti")
        self.tMap = maps("LM2")
        self.anti_tMap = maps("LM2_anti")
        self.best_score = 0
        self.realT = np.array([-1.5 , -2.5 , 90]) # real transformation

        self.N_eff = 1
        self.itr = 0
        self.prob = 0.1

        self.K = 1 # time step for norm2

        self.Nde = []
        self.NtPF = []
        self.resample_counter = 0
        self.init = True
        self.err_pf = []
        self.err_de = []
        while not rospy.is_shutdown():

        
            if self.oMap.started and self.tMap.started and self.anti_oMap.started and self.anti_tMap.started:
                
                #init nbrs for KNN
                self.nbrs = NearestNeighbors(n_neighbors= 1, algorithm='ball_tree').fit(self.oMap.map)
                #self.nbrs_anti = NearestNeighbors(n_neighbors= 1, algorithm='ball_tree').fit(self.anti_oMap.map)
                if self.init == True:
                    self.initialize_PF()
                    self.init = False
                # DE algorithm for finding best match
                result = differential_evolution(self.func_de, bounds = [(-15,15),(-15,15),(0,360)] ,maxiter= 10 ,popsize=3,tol=0.0001)
                self.T_de = [result.x[0] , result.x[1] , min(result.x[2], 360 - result.x[2])] 
                self.DEmap = self.tMap.rotate2(result.x)


                #print self.T_de
                self.predict()
                self.likelihood_PF()
                print "N_eff=:"+str(self.N_eff)
                self.resample_counter +=1
                #print resample_counter
                
                if self.N_eff < 0.001 and self.resample_counter>8:
                    self.resampling() # start re-sampling step 
                    self.resample_counter = 0
                    #self.gibbs_resampling_kmeans(iter_n=1)

                #self.norm2() # finding norm2

               # if self.K == 80 :

                #    self.save_data_DE()

                #self.K += 1

                #self.de_map = self.tMap.rotate2(result.x)
                self.plotmaps() # plot landmarks of maps.
                self.oMap.started = False
                self.tMap.started = False
                self.anti_oMap.started = False
                self.anti_tMap.started = False


                # c ,s = np.cos(self.T_tPF[2]) , np.sin(self.T_tPF[2])
                # R = np.array([[c,-s], [s, c]]) #Rotation matrix
                # gtt1 = np.matmul( ground_trouth_origin[0:2] - self.oMap.cm.T, R ) +  self.T_tPF[0:2] + self.tMap.cm.T# matrix multiplation
                # #gtt2 = np.matmul( ground_trouth_target[0:2] - self.tMap.cm.T, R ) +  self.T_tPF[0:2] + self.oMap.cm.T# matrix multiplation
                # #print "gtt1=:"+str((ground_trouth_origin[0:2] - self.oMap.cm.T))
                # #print "gtt2=:"+str((ground_trouth_target[0:2] - self.tMap.cm.T))
                # print "gtt1=:"+str(np.linalg.norm(gtt1 + ground_trouth_target[0:2]))



    def save_data_DE(self):

        if os.path.isfile('~/DE.csv'):
            with open('~/DE.csv', 'a') as f:
                self.save_stat_DE('~/DE.csv', ex = True, f=f)
        else:
            self.save_stat_DE('~/DE.csv', ex = False)

        print 'save data'

    def save_stat_DE(self,file_path, ex, f = None):

        data = {'De': self.Nde }
                
        df = pd.DataFrame(data, columns= ['De'])

        if ex==False:
            df.to_csv(file_path, sep='\t')
        else:
            df.to_csv(f, sep='\t', header=False)

    def save_data_tPF(self):

        if os.path.isfile('~/tPF.csv'):
            with open('~/tPF.csv', 'a') as f:
                self.save_stat_tPF('~/tPF.csv', ex = True, f=f)
        else:
            self.save_stat_tPF('~/tPF.csv', ex = False)

        print 'data saved'

    def save_stat_tPF(self,file_path, ex, f = None):

        data = {'tPF': self.NtPF}
                
        df = pd.DataFrame(data, columns= ['tPF'])

        if ex==False:
            df.to_csv(file_path, sep='\t')
        else:
            df.to_csv(f, sep='\t', header=False)

    def initialize_PF( self , angles = np.linspace(0 , 360 ,30 ) , xRange = np.linspace(-15 , 15 , 30) , yRange = np.linspace(-15 , 15 ,30) ,fire_up = 3000, Np = 500):
       
        # make a list of class rot(s)
        self.Rot = []
        Rot = []
        x0 = rot(angles[np.random.randint(len(angles))] ,
            xRange[np.random.randint(len(xRange))] ,
            yRange[np.random.randint(len(yRange))])
        tempMap = self.tMap.rotate(x0.x ,x0.y , x0.theta)
        tMap_anti = self.anti_tMap.rotate(x0.x ,x0.y , x0.theta)
        x0.weight2(self.oMap.map , tempMap, self.anti_oMap.map , tMap_anti , self.nbrs , 0.9,  1 )
        Rot.append(x0)
        i=0
        while i < fire_up:
            xt = rot(angles[np.random.randint(len(angles))] +0.5  * np.random.randn(),
                xRange[np.random.randint(len(xRange))] +0.5  * np.random.randn(),
                yRange[np.random.randint(len(yRange))]+0.5  * np.random.randn())
            tempMap = self.tMap.rotate(xt.x ,xt.y , xt.theta)
            tMap_anti = self.anti_tMap.rotate(xt.x ,xt.y , xt.theta)
            xt.weight2(self.oMap.map , tempMap, self.anti_oMap.map , tMap_anti , self.nbrs , 0.9,  1 )
            if xt.score>x0.score:
                Rot.append(xt)
                x0 = xt
                i+=1
            elif np.random.binomial(1, xt.score/x0.score) == 1:
                Rot.append(xt)
                x0 = xt
                i+=1
            else:
                Rot.append(x0)
                i+=1
        self.Rot = Rot[-Np:]
        self.pf_debug = np.zeros((len(self.Rot),4))
        print ("initialaize PF whith") , len(self.Rot) ,(" samples completed")

    def likelihood_PF(self):

        self.scores = []
        factor = np.power(1 - self.prob , self.resample_counter - self.itr )
        self.itr +=1 

        for i in self.Rot:    
            # 'tempMap' ->  map after transformation the secondery map [T(tMap)]:
            tempMap = self.tMap.rotate(i.x ,i.y , i.theta)
            #tMap_anti = self.anti_tMap.rotate(i.x ,i.y , i.theta)
            #i.weight2(self.oMap.map , tempMap, self.anti_oMap.map , tMap_anti , self.nbrs , 1.0,  1.0 )
            i.weight(self.oMap.map , tempMap ,self.nbrs , factor)
            self.scores.append(i.score) # add weights to array 
        w = np.array(self.scores)
        self.N_eff = 1/np.sum(np.power(w,2))
        maxt = max( self.Rot , key = operator.attrgetter('score') ) # finds partical with maximum score

        if maxt.score > self.best_score:          
        # check if there is a new partical thats better then previuos partical
            self.maxt = maxt
          
            self.maxMap = self.tMap.rotate(self.maxt.x ,self.maxt.y , self.maxt.theta )
            self.best_score =  maxt.score

            self.T_tPF = [self.maxt.x ,self.maxt.y , np.radians(self.maxt.theta)]
            print 'max W(tPF):' ,self.T_tPF

    def resampling(self):

        self.itr = 0
        W = self.scores/np.sum(self.scores) # Normalized scores for resampling 
        Np = len(self.Rot)
        index = np.random.choice(a = Np ,size = Np ,p = W ) # resample by score
        Rot_arr = [] # creat new temporery array for new sampels 

        for i in index:
            tmp_rot = copy.deepcopy(self.Rot[i])
            tmp_rot.add_noise() # add noise to current sample and set score to 0
            Rot_arr.append(tmp_rot) # resample by weights

        self.Rot = Rot_arr
        self.best_score = 0
        print 'resample done'

    def gibbs_resampling_kmeans(self, iter_n = 1):
        self.itr = 0
        Np = len(self.Rot)
        for iter in range(iter_n):
            kmeans = KMeans(n_clusters=5, init='k-means++', max_iter=300, n_init=10, random_state=0)
            kmeans.fit(self.pf_debug[:,0:2])
            index = np.random.choice(a = 5 ,size = Np)
            for i, idx in enumerate(index):
                self.Rot[i].theta += 0.5  * np.random.randn() + 0.5  * np.random.randn() + 90.0*np.random.choice(4,p = [0.6,0.1,0.2,0.1] )
                self.Rot[i].x = np.squeeze(kmeans.cluster_centers_[idx,0]) + np.random.normal(0,0.5)
                self.Rot[i].y = np.squeeze(kmeans.cluster_centers_[idx,1]) + np.random.normal(0,0.5)


            self.likelihood_PF()
            W = self.scores/np.sum(self.scores) # Normalized scores for resampling 
            Np = len(self.Rot)
            index = np.random.choice(a = Np ,size = Np ,p = W ) # resample by score
            Rot_arr = []
            Rot_arr = self.Rot # creat new temporery array for new sampels 

            

            # kmeans = KMeans(n_clusters=20, init='k-means++', max_iter=300, n_init=10, random_state=0)
            # kmeans.fit(self.pf_debug[:,2].reshape((-1,1)))
            # index = np.random.choice(a =20 ,size = Np)
            # for i, idx in enumerate(index):
            #     self.Rot[i].theta = np.squeeze(kmeans.cluster_centers_[idx]) + 0.5  * np.random.randn() + 90.0*np.random.choice(4,p = [0.8,0.05,0.1,0.05] )
            #     self.Rot[i].x += np.random.normal(0,0.1)
            #     self.Rot[i].y += np.random.normal(0,0.1)
            
            # self.likelihood_PF()
            # W = self.scores/np.sum(self.scores) # Normalized scores for resampling 
            # Np = len(self.Rot)
            # index = np.random.choice(a = Np ,size = Np ,p = W ) # resample by score
            # Rot_arr = []
            # Rot_arr = self.Rot # creat new temporery array for new sampels 


            print 'resample done'

    def gibbs_resampling_EM(self, iter_n = 1):
        self.itr = 0
        Np = len(self.Rot)
        for iter in range(iter_n):
            EM = BayesianGaussianMixture(n_components = 10)
            EM.fit(self.pf_debug[:,0:2])
            for i in range(Np):
                sample = EM.sample()
                self.Rot[i].theta += 0.5  * np.random.randn() + 90.0*np.random.choice(4,p = [0.8,0.05,0.1,0.05] )
                self.Rot[i].x = np.squeeze(sample[0]) 
                self.Rot[i].y = np.squeeze(sample[1]) 


            self.likelihood_PF()
            W = self.scores/np.sum(self.scores) # Normalized scores for resampling 
            Np = len(self.Rot)
            index = np.random.choice(a = Np ,size = Np ,p = W ) # resample by score
            Rot_arr = []
            Rot_arr = self.Rot # creat new temporery array for new sampels 

            

            kmeans = KMeans(n_clusters=4, init='k-means++', max_iter=300, n_init=10, random_state=0)
            kmeans.fit(self.pf_debug[:,2].reshape((-1,1)))
            index = np.random.choice(a = 4 ,size = Np)
            for i, idx in enumerate(index):
                self.Rot[i].theta = np.squeeze(kmeans.cluster_centers_[idx]) + 0.5  * np.random.randn()
                self.Rot[i].x += np.random.normal(0,0.01)
                self.Rot[i].y += np.random.normal(0,0.01)

            print 'resample done'

    def predict(self):        

        for i in range(len(self.Rot)):
            self.Rot[i].theta = (self.Rot[i].theta + 0.5  * np.random.randn()) % 360
            self.Rot[i].x += 0.2  * np.random.randn()
            self.Rot[i].y += 0.2  * np.random.randn()
            self.pf_debug[i,0] = self.Rot[i].x
            self.pf_debug[i,1] = self.Rot[i].y
            self.pf_debug[i,2] = self.Rot[i].theta
            self.pf_debug[i,3] = self.Rot[i].score
 
    def func_de(self , T):

        X = self.tMap.rotate2(T)

        var = 0.16        
        # fit data of map 2 to map 1  
        distances, indices = self.nbrs.kneighbors(X)
        # find the propability 
        prob = (1/(np.sqrt(2*np.pi*var)))*np.exp(-np.power(distances,2)/(2*var)) 
        # returm the 'weight' of this transformation
        wiegth = np.sum((prob)/prob.shape[0])+0.000001 #np.sum(prob)

        return -wiegth # de algo minimized this value

    def norm2(self):
        
        # find norm 2 of transformation 
        normDE = np.linalg.norm(self.T_de - self.realT) 
       # normtPF = np.linalg.norm(self.T_tPF - self.realT) 
        self.Nde.append(normDE)
       # self.NtPF.append(normtPF)
        #self.plot_norms(normDE , normtPF)
        
    def plot_norms(self , normDE , normtPF ):

        plt.axis([0 , 60, 0,  180])
       # plt.scatter(self.K ,normDE , color = 'b') # plot tPF map
        plt.scatter(self.K ,normtPF ,color = 'r') # plot origin map
        plt.pause(0.05)

        
 
    def plotmaps(self):

        #plt.axis([-60, 60, -60, 60])
        plt.subplot(2,2,1)
        #plt.axis([-50+self.oMap.cm[0], 50+self.oMap.cm[0], -50+self.oMap.cm[1], 50+self.oMap.cm[1]])
        plt.axis([-30, 30, -30, 30])
        plt.scatter(self.maxMap[: , 0] ,self.maxMap[:,1] , color = 'b') # plot tPF map
        plt.scatter(self.oMap.map[: , 0] ,self.oMap.map[:,1] ,color = 'r') # plot origin map
        plt.scatter(self.DEmap[: , 0] ,self.DEmap[:,1] ,color = 'g') # plot origin map
        plt.subplot(2,2,2)
        plt.scatter(self.pf_debug[:,0], self.pf_debug[:,1])
        plt.subplot(2,2,3)
        plt.scatter(self.pf_debug[:,2], self.pf_debug[:,3])



        c ,s = np.cos(self.T_tPF[2]) , np.sin(self.T_tPF[2])
        R = np.array([[c,-s], [s, c]]) #Rotation matrix

        ct ,st = np.cos(ground_trouth_target[2]) , np.sin(ground_trouth_target[2])
        Rt = np.array([[ct,-st], [st, ct]]) #Rotation matrix
        gtt1 =  np.matmul( ground_trouth_origin[0:2] - self.oMap.cm.T, R ) +  self.T_tPF[0:2]   -  np.matmul(ground_trouth_target[0:2] - self.tMap.cm.T, Rt)# matrix multiplation
        gtt_de = np.matmul( ground_trouth_origin[0:2] - self.oMap.cm.T, R ) +  self.T_de[0:2]  -  np.matmul(ground_trouth_target[0:2] - self.tMap.cm.T, Rt)# matrix multiplation
        
        self.err_pf.append(np.linalg.norm(gtt1 - ground_trouth_target[0:2]))
        self.err_de.append(np.linalg.norm(gtt_de - ground_trouth_target[0:2]))
        plt.subplot(2,2,4)
        plt.plot(self.err_pf, color = 'b')
        plt.plot(self.err_de, color = 'r')

        #plt.scatter(self.de_map[: , 0] ,self.de_map[:,1] , color = 'g') # plot DE map
        plt.pause(0.05)
        plt.clf()

class rot(object):
    
    # define 'rot' to be the class of the rotation for resamplimg filter

    def __init__(self , theta , xShift , yShift):
         self.theta = theta
         self.x = xShift
         self.y = yShift
         self.score = 0 



    def weight(self , oMap , tMap , nbrs , factor ):
        
        var = 0.05
        # fit data of map 2 to map 1  
        distances, indices = nbrs.kneighbors(tMap)
        # find the propability 
        prob = (1/(np.sqrt(2*np.pi*var)))*np.exp(-np.power(distances,2)/(2*var)) 
        # returm the 'weight' of this transformation
        wiegth = np.sum((prob)/prob.shape[0])+0.000001 #np.sum(prob) 
        
        self.score += wiegth * factor # sum up score

    def weight2(self , oMap , tMap, oMap_anti , tMap_anti , oMap_nbrs , alpha,  factor ):
        var1 = 0.1
        var2 = 0.016
        tMap_distances, _ = oMap_nbrs.kneighbors(tMap)
        tMap_anti_distances, _ = oMap_nbrs.kneighbors(tMap_anti)
        tMap_prob = (1/(np.sqrt(2*np.pi*var1)))*np.exp(-np.power(tMap_distances,2)/(2*var1)) 
        tMap_anti_prob = (1/(np.sqrt(2*np.pi*var2)))*np.exp(-np.power(tMap_anti_distances,2)/(2*var2))
        tMap_w = np.sum((tMap_prob)/tMap_prob.shape[0])+0.000001
        tMap_anti_w = np.exp(-(np.sum((tMap_anti_prob)/tMap_anti_prob.shape[0])+0.000001))      
        self.score += (tMap_w**alpha)*(tMap_anti_w**(1-alpha))* factor 

     
    def add_noise(self):
        self.x += 0.01 * np.random.randn()
        self.y += 0.01 * np.random.randn()
        self.theta = (self.theta+0.2  * np.random.randn() + 90.0*np.random.choice(4,p = [0.8,0.05,0.1,0.05] ))%360
        self.score=0

class maps:

    def __init__(self , topic_name ):
        
        self.check = True
        self.started = False # indicate if msg recived
        self.map = None #landmarks array
        self.cm = None
        self.name = topic_name

        rospy.Subscriber( topic_name , numpy_msg(Floats) , self.callback)
               
    def callback(self ,data):
        # reshape array from 1D to 2D
        landmarks = np.reshape(data.data, (-1, 2))
        # finding C.M for the first iterration

        if self.check:
            # determin the center of the map for initilaized map origin
            self.cm = np.sum(np.transpose(landmarks),axis=1)/len(landmarks)
            print ('set origin of: '), (self.name)
            self.check = False
            
        self.map = np.array(landmarks , dtype= "int32") - self.cm.T
        #print self.map
        self.started = True

    def rotate(self, xShift, yShift , RotationAngle): #rotat map for tPF
      
        theta = np.radians(RotationAngle) # angles to radians
        c ,s = np.cos(theta) , np.sin(theta)
        R = np.array([[c,-s], [s, c]]) #Rotation matrix
        RotatedLandmarks = np.matmul( self.map , R ) + np.array([xShift , yShift ]) # matrix multiplation

        return  RotatedLandmarks
   
    def rotate2(self, T): #rotat map for DE
      
        theta = np.radians(T[2]) # angles to radians
        c ,s = np.cos(theta) , np.sin(theta)
        R = np.array(((c,-s), (s, c))) #Rotation matrix
        RotatedLandmarks = np.matmul( self.map , R ) + np.array([T[0] , T[1]]) # matrix multiplation

        return  RotatedLandmarks
   
if __name__ == '__main__':
   
    print ("Running")
    PFtry = tPF() # 'tPF' : Partical Filter
    rospy.spin()