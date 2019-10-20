import torch
import torch.optim as optim
import torch.nn as nn

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation

from .networks import FCNN
from .neurodiffeq import diff


class DirichletBVP2D:
    """An Dirichlet boundary value problem on a 2-D orthogonal box where :math:`x\\in[x_0, x_1]` and :math:`y\\in[y_0, y_1]`
        We are solving :math:`u(x, t)` given:
        :math:`u(x, y)\\bigg|_{x = x_0} = f_0(y)`;
        :math:`u(x, y)\\bigg|_{x = x_1} = f_1(y)`;
        :math:`u(x, y)\\bigg|_{y = y_0} = g_0(x)`;
        :math:`u(x, y)\\bigg|_{y = y_1} = g_1(x)`.

        :param x_min: The lower bound of x, the :math:`x_0`.
        :type x_min: float
        :param x_min_val: The boundary value when :math:`x = x_0`, the :math:`f_0(y)`.
        :type x_min_val: function
        :param x_max: The upper bound of x, the :math:`x_1`.
        :type x_max: float
        :param x_max_val: The boundary value when :math:`x = x_1`, the :math:`f_1(y)`.
        :type x_max_val: function
        :param y_min: The lower bound of y, the :math:`y_0`.
        :type y_min: float
        :param y_min_val: The boundary value when :math:`y = y_0`, the :math:`g_0(x)`.
        :type y_min_val: function
        :param y_max: The upper bound of y, the :math:`y_1`.
        :type y_max: float
        :param y_max_val: The boundary value when :math:`y = y_1`, the :math:`g_1(x)`.
        :type y_max_val: function
    """

    def __init__(self, x_min, x_min_val, x_max, x_max_val, y_min, y_min_val, y_max, y_max_val):
        """Initializer method
        """
        self.x_min, self.x_min_val = x_min, x_min_val
        self.x_max, self.x_max_val = x_max, x_max_val
        self.y_min, self.y_min_val = y_min, y_min_val
        self.y_max, self.y_max_val = y_max, y_max_val

    def enforce(self, net, x, y):
        r"""Enforce the output of a neural network to satisfy the boundary condition.

            :param net: The neural network that approximates the ODE.
            :type net: `torch.nn.Module`
            :param x: X-coordinates of the points where the neural network output is evaluated.
            :type x: `torch.tensor`
            :param y: Y-coordinates of the points where the neural network output is evaluated.
            :type y: `torch.tensor`
            :return: The modified output which now satisfies the boundary condition.
            :rtype: `torch.tensor`

            .. note::
                `enforce` is meant to be called by the function `solve2D`.
        """
        xys = torch.cat((x, y), 1)
        u = net(xys)
        x_tilde = (x-self.x_min) / (self.x_max-self.x_min)
        y_tilde = (y-self.y_min) / (self.y_max-self.y_min)
        Axy = (1-x_tilde)*self.x_min_val(y) + x_tilde*self.x_max_val(y) + \
              (1-y_tilde)*( self.y_min_val(x) - ((1-x_tilde)*self.y_min_val(self.x_min * torch.ones_like(x_tilde))
                                                  + x_tilde *self.y_min_val(self.x_max * torch.ones_like(x_tilde))) ) + \
                 y_tilde *( self.y_max_val(x) - ((1-x_tilde)*self.y_max_val(self.x_min * torch.ones_like(x_tilde))
                                                  + x_tilde *self.y_max_val(self.x_max * torch.ones_like(x_tilde))) )
        return Axy + x_tilde*(1-x_tilde)*y_tilde*(1-y_tilde)*u


class IBVP1D:
    """An initial boundary value problem on a 1-D range where :math:`x\\in[x_0, x_1]` and time starts at :math:`t_0`
            We are solving :math:`u(x, t)` given:
            :math:`u(x, t)\\bigg|_{t = t_0} = u_0(x)`;
            :math:`u(x, t)\\bigg|_{x = x_0} = g(t)` or :math:`\\displaystyle\\frac{\\partial u(x, t)}{\\partial x}\\bigg|_{x = x_0} = g(t)`;
            :math:`u(x, t)\\bigg|_{x = x_1} = h(t)` or :math:`\\displaystyle\\frac{\\partial u(x, t)}{\\partial x}\\bigg|_{x = x_1} = h(t)`.

            :param x_min: The lower bound of x, the :math:`x_0`.
            :type x_min: float
            :param x_max: The upper bound of x, the :math:`x_1`.
            :type x_max: float
            :param t_min: The initial time, the :math:`t_0`.
            :type t_min: float
            :param t_min_val: The initial condition, the :math:`u_0(x)`.
            :type t_min_val: function
            :param x_min_val: The Dirichlet boundary condition when :math:`x = x_0`, the :math:`u(x, t)\\bigg|_{x = x_0}`, defaults to None.
            :type x_min_val: function, optional
            :param x_min_prime: The Neumann boundary condition when :math:`x = x_0`, the :math:`\\displaystyle\\frac{\\partial u(x, t)}{\\partial x}\\bigg|_{x = x_0}`, defaults to None.
            :type x_min_prime: function, optional
            :param x_max_val: The Dirichlet boundary condition when :math:`x = x_1`, the :math:`u(x, t)\\bigg|_{x = x_1}`, defaults to None.
            :type x_max_val: function, optioonal
            :param x_max_prime: The Neumann boundary condition when :math:`x = x_1`, the :math:`\\displaystyle\\frac{\\partial u(x, t)}{\\partial x}\\bigg|_{x = x_1}`, defaults to None.
            :type x_max_prime: function, optional
            :raises ValueError: When provided problem is over-conditioned.
            :raises NotImplementedError: When unimplemented boundary conditions are configured.
        """

    def __init__(
            self, x_min, x_max, t_min, t_min_val,
            x_min_val=None, x_min_prime=None,
            x_max_val=None, x_max_prime=None,

    ):
        r"""Initializer method

        .. note::
            A instance method `enforce` is dynamically created to enforce initial and boundary conditions. It will be called by the function `solve2D`.
        """
        self.x_min, self.x_min_val, self.x_min_prime = x_min, x_min_val, x_min_prime
        self.x_max, self.x_max_val, self.x_max_prime = x_max, x_max_val, x_max_prime
        self.t_min, self.t_min_val = t_min, t_min_val
        if self.x_min_val and self.x_max_val:
            if self.x_min_prime or self.x_max_prime:
                raise ValueError('Problem is over-conditioned.')
            self.enforce = self._enforce_dd
        elif self.x_min_val and self.x_max_prime:
            if self.x_min_prime or self.x_max_val:
                raise ValueError('Problem is over-conditioned.')
            self.enforce = self._enforce_dn
        elif self.x_min_prime and self.x_max_val:
            if self.x_min_val or self.x_max_prime:
                raise ValueError('Problem is over-conditioned.')
            self.enforce = self._enforce_nd
        elif self.x_min_prime and self.x_max_prime:
            if self.x_min_val or self.x_max_val:
                raise ValueError('Problem is over-conditioned.')
            self.enforce = self._enforce_nn
        else:
            raise NotImplementedError('Sorry, this boundary condition is not implemented.')

    def _enforce_dd(self, net, x, t):
        xts = torch.cat((x, t), 1)
        uxt = net(xts)

        t_ones = torch.ones_like(t, requires_grad=True)
        t_ones_min = self.t_min * t_ones

        x_tilde = (x - self.x_min) / (self.x_max - self.x_min)
        t_tilde = t - self.t_min

        Axt = self.t_min_val(x) + \
            x_tilde     * (self.x_max_val(t) - self.x_max_val(t_ones_min)) + \
            (1-x_tilde) * (self.x_min_val(t) - self.x_min_val(t_ones_min))
        return Axt + x_tilde * (1 - x_tilde) * (1 - torch.exp(-t_tilde)) * uxt

    def _enforce_dn(self, net, x, t):
        xts = torch.cat((x, t), 1)
        uxt = net(xts)

        x_ones = torch.ones_like(x, requires_grad=True)
        t_ones = torch.ones_like(t, requires_grad=True)
        x_ones_max = self.x_max * x_ones
        t_ones_min = self.t_min * t_ones
        xmaxts  = torch.cat((x_ones_max, t), 1)
        uxmaxt  = net(xmaxts)

        x_tilde = (x-self.x_min) / (self.x_max-self.x_min)
        t_tilde = t-self.t_min

        Axt = (self.x_min_val(t) - self.x_min_val(t_ones_min)) + self.t_min_val(x) + \
            x_tilde * (self.x_max-self.x_min) * (self.x_max_prime(t) - self.x_max_prime(t_ones_min))
        return Axt + x_tilde*(1-torch.exp(-t_tilde))*(
            uxt - (self.x_max-self.x_min)*diff(uxmaxt, x_ones_max) - uxmaxt
        )

    def _enforce_nd(self, net, x, t):
        xts = torch.cat((x, t), 1)
        uxt = net(xts)

        x_ones = torch.ones_like(x, requires_grad=True)
        t_ones = torch.ones_like(t, requires_grad=True)
        x_ones_min = self.x_min * x_ones
        t_ones_min = self.t_min * t_ones
        xmints = torch.cat((x_ones_min, t), 1)
        uxmint = net(xmints)

        x_tilde = (x - self.x_min) / (self.x_max - self.x_min)
        t_tilde = t - self.t_min

        Axt = (self.x_max_val(t) - self.x_max_val(t_ones_min)) + self.t_min_val(x) + \
              (x_tilde - 1) * (self.x_max - self.x_min) * (self.x_min_prime(t) - self.x_min_prime(t_ones_min))
        return Axt + (1 - x_tilde) * (1 - torch.exp(-t_tilde)) * (
                uxt + (self.x_max - self.x_min) * diff(uxmint, x_ones_min) - uxmint
        )

    def _enforce_nn(self, net, x, t):
        xts = torch.cat((x, t), 1)
        uxt = net(xts)

        x_ones = torch.ones_like(x, requires_grad=True)
        t_ones = torch.ones_like(t, requires_grad=True)
        x_ones_min = self.x_min * x_ones
        x_ones_max = self.x_max * x_ones
        t_ones_min = self.t_min * t_ones
        xmints = torch.cat((x_ones_min, t), 1)
        xmaxts = torch.cat((x_ones_max, t), 1)
        uxmint = net(xmints)
        uxmaxt = net(xmaxts)

        x_tilde = (x - self.x_min) / (self.x_max - self.x_min)
        t_tilde = t - self.t_min

        Axt = self.t_min_val(x) - 0.5 * (1 - x_tilde) ** 2 * (self.x_max - self.x_min) * (
                self.x_min_prime(t) - self.x_min_prime(t_ones_min)
        ) + 0.5 * x_tilde ** 2 * (self.x_max - self.x_min) * (
                      self.x_max_prime(t) - self.x_max_prime(t_ones_min)
              )
        return Axt + (1 - torch.exp(-t_tilde)) * (
                uxt - x_tilde * (self.x_max - self.x_min) * diff(uxmint, x_ones_min) \
                + 0.5 * x_tilde ** 2 * (self.x_max - self.x_min) * (
                        diff(uxmint, x_ones_min) - diff(uxmaxt, x_ones_max)
                ))


class ExampleGenerator2D:
    """An example generator for generating 2-D training points.

        :param grid: The discretization of the 2 dimensions, if we want to generate points on a :math:`m \\times n` grid, then `grid` is `(m, n)`, defaults to `(10, 10)`.
        :type grid: tuple[int, int], optional
        :param xy_min: The lower bound of 2 dimensions, if we only care about :math:`x \\geq x_0` and :math:`y \\geq y_0`, then `xy_min` is `(x_0, y_0)`, defaults to `(0.0, 0.0)`.
        :type xy_min: tuple[float, float], optional
        :param xy_max: The upper boound of 2 dimensions, if we only care about :math:`x \\leq x_1` and :math:`y \\leq y_1`, then `xy_min` is `(x_1, y_1)`, defaults to `(1.0, 1.0)`.
        :type xy_max: tuple[float, float], optional
        :param method: The distribution of the 2-D points generated.
            If set to 'equally-spaced', the points will be fixed to the grid specified.
            If set to 'equally-spaced-noisy', a normal noise will be added to the previously mentioned set of points, defaults to 'equally-spaced-noisy'.
        :type method: str, optional
        :raises ValueError: When provided with an unknown method.
    """

    def __init__(self, grid=(10, 10), xy_min=(0.0, 0.0), xy_max=(1.0, 1.0), method='equally-spaced-noisy'):
        r"""Initializer method

        .. note::
            A instance method `get_examples` is dynamically created to generate 2-D training points. It will be called by the function `solve2D`.
        """
        self.size = grid[0] * grid[1]

        if method == 'equally-spaced':
            x = torch.linspace(xy_min[0], xy_max[0], grid[0], requires_grad=True)
            y = torch.linspace(xy_min[1], xy_max[1], grid[1], requires_grad=True)
            grid_x, grid_y = torch.meshgrid(x, y)
            self.grid_x, self.grid_y = grid_x.flatten(), grid_y.flatten()

            self.get_examples = lambda: (self.grid_x, self.grid_y)

        elif method == 'equally-spaced-noisy':
            x = torch.linspace(xy_min[0], xy_max[0], grid[0], requires_grad=True)
            y = torch.linspace(xy_min[1], xy_max[1], grid[1], requires_grad=True)
            grid_x, grid_y = torch.meshgrid(x, y)
            self.grid_x, self.grid_y = grid_x.flatten(), grid_y.flatten()

            self.noise_xmean = torch.zeros(self.size)
            self.noise_ymean = torch.zeros(self.size)
            self.noise_xstd = torch.ones(self.size) * ((xy_max[0] - xy_min[0]) / grid[0]) / 4.0
            self.noise_ystd = torch.ones(self.size) * ((xy_max[1] - xy_min[1]) / grid[1]) / 4.0
            self.get_examples = lambda: (
                self.grid_x + torch.normal(mean=self.noise_xmean, std=self.noise_xstd),
                self.grid_y + torch.normal(mean=self.noise_ymean, std=self.noise_ystd)
            )
        else:
            raise ValueError(f'Unknown method: {method}')


class Monitor2D:
    """A monitor for checking the status of the neural network during training.

    :param xy_min: The lower bound of 2 dimensions, if we only care about :math:`x \\geq x_0` and :math:`y \\geq y_0`, then `xy_min` is `(x_0, y_0)`.
    :type xy_min: tuple[float, float], optional
    :param xy_max: The upper boound of 2 dimensions, if we only care about :math:`x \\leq x_1` and :math:`y \\leq y_1`, then `xy_min` is `(x_1, y_1)`.
    :type xy_max: tuple[float, float], optional
    :param check_every: The frequency of checking the neural network represented by the number of epochs between two checks, defaults to 100.
    :type check_every: int, optional
    """

    def __init__(self, xy_min, xy_max, check_every=100):
        """Initializer method
        """
        self.check_every = check_every
        self.fig = plt.figure(figsize=(20, 8))
        self.ax1 = self.fig.add_subplot(121)
        self.ax2 = self.fig.add_subplot(122)
        self.cb1 = None
        # input for neural network
        gen = ExampleGenerator2D([32, 32], xy_min, xy_max, method='equally-spaced')
        xs_ann, ys_ann = gen.get_examples()
        self.xs_ann, self.ys_ann = xs_ann.reshape(-1, 1), ys_ann.reshape(-1, 1)
        self.xy_ann = torch.cat((self.xs_ann, self.ys_ann), 1)

    def check(self, net, condition, loss_history):
        r"""Draw 2 plots: One shows the shape of the current solution (with heat map). The other shows the history training loss and validation loss.

        :param net: The neural networks that approximates the PDE.
        :type net: `torch.nn.Module`
        :param condition: The initial/boundary condition of the PDE.
        :type condition: `neurodiff.pde.DirichletBVP2D` or `neurodiff.pde.IBVP1D`]
        :param loss_history: The history of training loss and validation loss. The 'train' entry is a list of training loss and 'valid' entry is a list of validation loss.
        :type loss_history: dict['train': list[float], 'valid': list[float]]

        .. note::
            `check` is meant to be called by the function `solve2D`.
        """
        us = condition.enforce(net, self.xs_ann, self.ys_ann)
        us = us.detach().numpy().flatten()

        self.ax1.clear()
        cax1 = self.ax1.matshow(us.reshape((32, 32)), cmap='hot', interpolation='nearest')
        if self.cb1: self.cb1.remove()
        self.cb1 = self.fig.colorbar(cax1, ax=self.ax1)
        self.ax1.set_title('u(x, y)')

        self.ax2.clear()
        self.ax2.plot(loss_history['train'], label='training loss')
        self.ax2.plot(loss_history['valid'], label='validation loss')
        self.ax2.set_title('loss during training')
        self.ax2.set_ylabel('loss')
        self.ax2.set_xlabel('epochs')
        self.ax2.set_yscale('log')
        self.ax2.legend()

        self.fig.canvas.draw()


def solve2D(
        pde, condition, xy_min, xy_max,
        net=None, train_generator=None, shuffle=True, valid_generator=None, optimizer=None, criterion=None, batch_size=16,
        max_epochs=1000,
        monitor=None, return_internal=False
):
    """Train a neural network to solve a PDE with 2 independent variables.

    :param pde: The PDE to solve. If the PDE is :math:`F(u, x, y) = 0` where :math:`u` is the dependent variable and :math:`x` and :math:`y` are the independent variables,
        then `pde` should be a function that maps :math:`(u, x, y)` to :math:`F(u, x, y)`.
    :type pde: function
    :param condition: The initial/boundary condition.
    :type condition: `neurodiff.pde.DirichletBVP2D` or `neurodiff.pde.IBVP1D`
    :param xy_min: The lower bound of 2 dimensions, if we only care about :math:`x \\geq x_0` and :math:`y \\geq y_0`, then `xy_min` is `(x_0, y_0)`.
    :type xy_min: tuple[float, float], optional
    :param xy_max: The upper boound of 2 dimensions, if we only care about :math:`x \\leq x_1` and :math:`y \\leq y_1`, then `xy_min` is `(x_1, y_1)`.
    :type xy_max: tuple[float, float], optional
    :param net: The neural network used to approximate the solution, defaults to None.
    :type net: `torch.nn.Module`, optional
    :param train_generator: The example generator to generate 1-D training points, default to None.
    :type train_generator: `neurodiff.pde.ExampleGenerator2D`, optional
    :param shuffle: Whether to shuffle the training examples every epoch, defaults to True.
    :type shuffle: bool, optional
    :param valid_generator: The example generator to generate 1-D validation points, default to None.
    :type valid_generator: `neurodiff.pde.ExampleGenerator2D`, optional
    :param optimizer: The optimization method to use for training, defaults to None.
    :type optimizer: `torch.optim.Optimizer`, optional
    :param criterion: The loss function to use for training, defaults to None.
    :type criterion: `torch.nn.modules.loss._Loss`, optional
    :param batch_size: The size of the mini-batch to use, defaults to 16.
    :type batch_size: int, optional
    :param max_epochs: The maximum number of epochs to train, defaults to 1000.
    :type max_epochs: int, optional
    :param monitor: The monitor to check the status of nerual network during training, defaults to None.
    :type monitor: `neurodiffeq.pde.Monitor2D`, optional
    :param return_internal: Whether to return the nets, conditions, training generator, validation generator, optimizer and loss function, defaults to False.
    :type return_internal: bool, optional
    :return: The solution of the PDE. The history of training loss and validation loss.
        Optionally, the nets, conditions, training generator, validation generator, optimizer and loss function.
        The solution is a function that has the signature `solution(xs, ys, as_type)`.
        `xs (torch.tensor)` and `ys (torch.tensor)` are the points on which :math:`u(x, y)` is evaluated.
        `as_type (str)` indicates whether the returned value is a `torch.tensor` ('tf') or `numpy.array` ('np').
    :rtype: tuple[function, dict]; or tuple[function, dict, dict]
    """

    # default values
    if not net:
        net = FCNN(n_input_units=2, n_hidden_units=32, n_hidden_layers=1, actv=nn.Tanh)
    if not train_generator:
        train_generator = ExampleGenerator2D([32, 32], xy_min, xy_max, method='equally-spaced-noisy')
    if not valid_generator:
        valid_generator = ExampleGenerator2D([32, 32], xy_min, xy_max, method='equally-spaced')
    if not optimizer:
        optimizer = optim.Adam(net.parameters(), lr=0.001)
    if not criterion:
        criterion = nn.MSELoss()

    if return_internal:
        internal = {
            'net': net,
            'condition': condition,
            'train_generator': train_generator,
            'valid_generator': valid_generator,
            'optimizer': optimizer,
            'criterion': criterion
        }

    n_examples_train = train_generator.size
    n_examples_valid = valid_generator.size
    train_zeros = torch.zeros(batch_size)
    valid_zeros = torch.zeros(n_examples_valid)

    loss_history = {'train': [], 'valid': []}

    for epoch in range(max_epochs):
        train_loss_epoch = 0.0

        train_examples_x, train_examples_y = train_generator.get_examples()
        train_examples_x, train_examples_y = train_examples_x.reshape((-1, 1)), train_examples_y.reshape((-1, 1))
        idx = np.random.permutation(n_examples_train) if shuffle else np.arange(n_examples_train)
        batch_start, batch_end = 0, batch_size
        while batch_start < n_examples_train:

            if batch_end > n_examples_train:
                batch_end = n_examples_train
            batch_idx = idx[batch_start:batch_end]
            xs, ys = train_examples_x[batch_idx], train_examples_y[batch_idx]

            us = condition.enforce(net, xs, ys)

            Fuxy = pde(us, xs, ys)
            loss = criterion(Fuxy, train_zeros)
            train_loss_epoch += loss.item() * (batch_end-batch_start)/n_examples_train

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            batch_start += batch_size
            batch_end += batch_size

        loss_history['train'].append(train_loss_epoch)

        # calculate the validation loss
        valid_examples_x, valid_examples_y = valid_generator.get_examples()
        xs, ys = valid_examples_x.reshape((-1, 1)), valid_examples_y.reshape((-1, 1))
        us = condition.enforce(net, xs, ys)
        Fuxy = pde(us, xs, ys)
        valid_loss_epoch = criterion(Fuxy, valid_zeros).item()

        loss_history['valid'].append(valid_loss_epoch)

        if monitor and epoch % monitor.check_every == 0:
            monitor.check(net, condition, loss_history)

    def solution(xs, ys, as_type='tf'):
        original_shape = xs.shape
        if not isinstance(xs, torch.Tensor): xs = torch.tensor([xs], dtype=torch.float32)
        if not isinstance(ys, torch.Tensor): ys = torch.tensor([ys], dtype=torch.float32)
        xs, ys = xs.reshape(-1, 1), ys.reshape(-1, 1)
        us = condition.enforce(net, xs, ys)
        if   as_type == 'tf':
            return us.reshape(original_shape)
        elif as_type == 'np':
            return us.detach().numpy().reshape(original_shape)
        else:
            raise ValueError("The valid return types are 'tf' and 'np'.")

    if return_internal:
        return solution, loss_history, internal
    else:
        return solution, loss_history


def make_animation(solution, xs, ts):
    """Create animation of 1-D time-dependent problems.

    :param solution: solution function returned by `solve2D` (for a 1-D time-dependent problem).
    :type solution: function
    :param xs: The locations to evaluate solution.
    :type xs: `numpy.array`
    :param ts: The time points to evaluate solution.
    :type ts: `numpy.array`
    :return: The animation.
    :rtype: `matplotlib.animation.FuncAnimation`
    """

    xx, tt = np.meshgrid(xs, ts)
    sol_net = solution(xx, tt, as_type='np')

    def u_gen():
        for i in range( len(sol_net) ):
            yield sol_net[i]

    fig, ax = plt.subplots()
    line, = ax.plot([], [], lw=2)

    umin, umax = sol_net.min(), sol_net.max()
    scale = umax - umin
    ax.set_ylim(umin-scale*0.1, umax+scale*0.1)
    ax.set_xlim(xs.min(), xs.max())
    def run(data):
        line.set_data(xs, data)
        return line,

    return animation.FuncAnimation(
        fig, run, u_gen, blit=True, interval=50, repeat=False
    )
