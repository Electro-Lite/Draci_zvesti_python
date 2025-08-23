# https://neat-python.readthedocs.io/en/latest/xor_example.html
import neat
import os
from   time import time,ctime
import pickle
import game
import winsound
import sys



def eval_genomes_ai(genomes, config):
    """
    Run each genome against eachother one time to determine the fitness.
    """

    for i, (genome_id1, genome1) in enumerate(genomes):
        print(round(i/len(genomes) * 100), end=" ")
        if(i==0):
            winsound.Beep(5000, 500)
            
        genome1.fitness = 0
        for genome_id2, genome2 in genomes[min(i+1, len(genomes) - 1):]:
            genome2.fitness = 0 if genome2.fitness == None else genome2.fitness

            player_1=game.player(1,"ai")
            player_2=game.player(2,"ai")
            player_1.net=neat.nn.FeedForwardNetwork.create(genome1, config)
            player_2.net=neat.nn.FeedForwardNetwork.create(genome2, config)
            sys.stdout=None
            game.run(player_1, player_2)
            sys.stdout=sys.__stdout__
            #calculate fitness
            player_1.fitness += 10 * (player_1.score - 1)
            player_2.fitness += 10 * (player_2.score - 1)
            
            genome1.fitness += player_1.fitness
            genome2.fitness += player_2.fitness
            
def eval_genomes_rnd(genomes, config):
    """
    Run each genome against random
    """

    for i, (genome_id1, genome1) in enumerate(genomes):
        genome1.fitness = 0
        if(i==0):
            print(ctime(time()))
        for j in range(50):

            player_1=game.player(1,"ai")
            player_2=game.player(2,"rnd")
            player_1.net=neat.nn.FeedForwardNetwork.create(genome1, config)
            sys.stdout=None
            game.run(player_1, player_2)
            sys.stdout=sys.__stdout__
            #calculate fitness
            player_1.fitness += 10 * (player_1.score - player_2.score)
            
            genome1.fitness += player_1.fitness
            

def run_neat(config):
    p = neat.Checkpointer.restore_checkpoint('neat-checkpoint-rnd6_ext-1376')
    p.config = config
    #p = neat.Population(config)
    p.add_reporter(neat.StdOutReporter(True))
    #stats = neat.StatisticsReporter()
    #p.add_reporter(stats)
    p.add_reporter(neat.Checkpointer(generation_interval=10,filename_prefix="neat-checkpoint-rnd6_ext-"))

    report = ""
    timeTaken= time()
    
    winner = p.run(eval_genomes_rnd, 1)
    
    with open("best_rnd6_ext.pickle", "wb") as f:
        pickle.dump(winner, f)
        
    with open("record.txt", "w") as f:
        timeTaken= time() - timeTaken
        report+= "training time: " + str(timeTaken) +"s\n"
        f.write(report)


def test_best_network(config):
    with open("best_rnd6_ext.pickle", "rb") as f:
        winner = pickle.load(f)
    winner_net = neat.nn.FeedForwardNetwork.create(winner, config)
    score = [0,0,0]
    for i in range(0,10000):
        player_1=game.player(1,"ai")
        player_1.net=winner_net
        player_2=game.player(2,"rnd")
        sys.stdout=None
        game.run(player_1, player_2)
        sys.stdout=sys.__stdout__
        if  (player_1.score > player_2.score):
            score[0]+=1
        elif(player_1.score < player_2.score):
            score[2]+=1
        else:
            score[1]+=1
    print("final score is:")
    print("ai   :" + str(int(score[0]/100))+"%")
    print("draws:" + str(int(score[1]/100))+"%")
    print("rnd  :" + str(int(score[2]/100))+"%")
            
            
        
    


if __name__ == '__main__':
    local_dir   = os.path.dirname(__file__)
    config_path = os.path.join(local_dir, 'config.txt')

    config = neat.Config(neat.DefaultGenome, neat.DefaultReproduction,
                         neat.DefaultSpeciesSet, neat.DefaultStagnation,
                         config_path)
    #run_neat(config)
    test_best_network(config)
    #with open("record.txt", "r") as f:
    #   print(f.read())
    #winsound.Beep(1000, 3000)
    #os.system("shutdown /s /t 1")