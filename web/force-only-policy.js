(() => {
      const solver=document.querySelector('#genericSolverMethod'),connection=document.querySelector('#genericConnectionType');
      for(const option of [...solver.options])if(option.value!=='standalone')option.remove();solver.value='standalone';
      for(const option of [...connection.options])if(option.value!=='integralHubRingButtWeld')option.remove();connection.value='integralHubRingButtWeld';
      const mode=document.querySelector('#solidCouplingMode');mode.value='forceSubmodel';
      const shear=document.querySelector('#solidShearDistribution');for(const o of [...shear.options])if(o.value!=='saintVenantAnnulus')o.remove();shear.value='saintVenantAnnulus';
      window.FrameCAESolidPanel?.refresh();
    })();